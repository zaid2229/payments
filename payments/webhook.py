import frappe
import json
import stripe

@frappe.whitelist(allow_guest=True)
def handle_stripe_webhook():
    try:
        # Parse incoming request
        payload = frappe.request.data.decode("utf-8")  # Decode raw payload
        sig_header = frappe.get_request_header('STRIPE_SIGNATURE')

        if not sig_header:
            frappe.log_error("Missing STRIPE_SIGNATURE header", "Stripe Webhook Error")
            frappe.throw("Invalid webhook request")

        # Retrieve Stripe secret
        stripe_settings = frappe.get_doc("Stripe Settings", 'Bayaan Test Mode')

        stripe.api_key = stripe_settings.get_password(fieldname="secret_key", raise_exception=False)
        endpoint_secret = stripe_settings.webhook_secret

        try:
            # Verify webhook signature
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        except stripe.error.SignatureVerificationError as e:
            frappe.log_error({
                "payload": payload,
                "sig_header": sig_header,
                "endpoint_secret": endpoint_secret,
                "error": str(e),
            }, "Stripe Signature Verification Error")
            raise frappe.ValidationError("Invalid signature")

        # Handle the event
        event_type = event.get("type")
        if event_type == "invoice.payment_succeeded":
            process_invoice_payment(event["data"]["object"])

        return "Webhook processed successfully"

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Stripe Webhook Error")
        raise frappe.ValidationError(f"Error processing webhook: {str(e)}")



def process_invoice_payment(invoice_data):
    """Update ERPNext invoice and create GL entry"""
    try:
        stripe_customer_id = invoice_data.get("customer")
        amount_received = invoice_data.get("amount_paid") / 100  # Convert from cents to dollars
        payment_date = frappe.utils.datetime.datetime.fromtimestamp(invoice_data.get("created"))

        # Fetch the Stripe Customer document
        stripe_customer = frappe.get_doc("Stripe Customers", stripe_customer_id)


        if not stripe_customer.invoice:
            frappe.throw("No selected invoice in Stripe Customer.")

        # Process the selected invoice
        update_next_billing_date(stripe_customer, payment_date)
        process_selected_invoice(stripe_customer.invoice, amount_received, payment_date)

        # Filter other sales invoices
        filtered_invoices = filter_sales_invoices(stripe_customer_id, payment_date)

        for invoice in filtered_invoices:
            process_selected_invoice(invoice.name,amount_received,payment_date)
        

                # Update the next billing date in Stripe Customer
        

        frappe.msgprint(f"Filtered invoices: {len(filtered_invoices)}")

    except Exception as e:
        frappe.log_error(f"Error processing invoice: {str(e)}", "Stripe Invoice Processing Error")
        raise frappe.ValidationError(f"Error processing invoice: {str(e)}")


def process_selected_invoice(invoice_name, amount_received, payment_date):
    try:
        # Fetch the Sales Invoice document
        sales_invoice = frappe.get_doc("Sales Invoice", invoice_name)

        # Check if the invoice is already paid
        if sales_invoice.status == "Paid":
            frappe.msgprint(f"Invoice {sales_invoice.name} is already paid.")
            return

        # # Mark the invoice as Paid
        # sales_invoice.status = "Paid"
        # sales_invoice.outstanding_amount = 0
        # sales_invoice.save(ignore_permissions=True)

        # Create GL Entry
        create_gl_entry(sales_invoice.name, amount_received, payment_date)

        frappe.msgprint(f"Invoice {sales_invoice.name} marked as Paid and GL Entry created.")

    except Exception as e:
        frappe.log_error(f"Error processing selected invoice: {str(e)}", "Invoice Processing Error")
        raise frappe.ValidationError(f"Error processing selected invoice: {str(e)}")


def filter_sales_invoices(stripe_id, payment_date):
    try:
        # Fetch Sales Invoices with matching criteria
        sales_invoices = frappe.get_all(
            "Sales Invoice",
            filters={
                "custom_stripe_id": stripe_id,
                "custom_invoice_billing_date": payment_date,
                "status": ["not in", ["Draft", "Cancelled", "Paid"]]
            },
            fields=["name", "custom_invoice_billing_date", "grand_total"]
        )

        if not sales_invoices:
            frappe.msgprint("No matching sales invoices found.")
            return []



        frappe.msgprint(f"Found {len(sales_invoices)} invoices for Stripe Customer ID: {stripe_id}.")
        return sales_invoices

    except Exception as e:
        frappe.log_error(f"Error filtering sales invoices: {str(e)}", "Invoice Filtering Error")
        raise frappe.ValidationError(f"Error filtering sales invoices: {str(e)}")



def create_gl_entry(invoice_name, amount, payment_date):
    try:
        from frappe.utils import flt

        # Fetch accounts
        receivable_account = frappe.get_value("Company", frappe.get_value("Sales Invoice", invoice_name, "company"), "default_receivable_account")
        payment_gateway_account = frappe.get_all(
            "Payment Gateway Account", filters={"is_default": 1}, fields=["payment_account"]
        )[0].payment_account

        # Prepare GL Entries
        gl_entries = [
            {
                "account": receivable_account,
                "party_type": "Customer",
                "party": frappe.get_value("Sales Invoice", invoice_name, "customer"),
                "debit": 0,
                "credit": flt(amount),
                "voucher_type": "Sales Invoice",
                "voucher_no": invoice_name,
                "posting_date": payment_date,
                "remarks": "Payment received via Stripe",
            },
            {
                "account": payment_gateway_account,
                "debit": flt(amount),
                "credit": 0,
                "voucher_type": "Sales Invoice",
                "voucher_no": invoice_name,
                "posting_date": payment_date,
                "remarks": "Payment received via Stripe",
            },
        ]

        # Insert GL Entries
        for entry in gl_entries:
            gl_entry = frappe.get_doc({"doctype": "GL Entry", **entry})
            gl_entry.insert(ignore_permissions=True)
            gl_entry.submit()

        # Update Sales Invoice status
        frappe.db.set_value("Sales Invoice", invoice_name, "status", "Paid")
        frappe.db.set_value("Sales Invoice", invoice_name, "outstanding_amount", 0)
        frappe.db.commit()

        frappe.msgprint(f"GL Entry created for Invoice {invoice_name}.")

    except Exception as e:
        frappe.log_error(f"Error creating GL Entry: {str(e)}", "GL Entry Error")
        raise frappe.ValidationError(f"Error creating GL Entry: {str(e)}")




def get_exchange_rate(from_currency, to_currency):
    """Utility function to get the exchange rate between two currencies."""
    return frappe.db.get_value("Currency Exchange", {
        "from_currency": from_currency,
        "to_currency": to_currency
    }, "exchange_rate") or 1.0  # Default to 1 if no rate found

from frappe.utils import add_months

def update_next_billing_date(stripe_customer, payment_date):
    
    """Set the next billing date in the Stripe Customer doctype"""
    try:
        # Calculate the next billing date (e.g., monthly subscription)
        current_billing_date = payment_date
        next_billing_date = add_months(current_billing_date, 1)

        # Update the next billing date in the Stripe Customer
        stripe_customer.next_billing_date = next_billing_date
        stripe_customer.save(ignore_permissions=True)

        frappe.msgprint(f"Next billing date set to {next_billing_date} for Stripe Customer {stripe_customer.name}")

    except Exception as e:
        frappe.log_error(f"Error updating next billing date: {str(e)}", "Next Billing Date Error")
        raise frappe.ValidationError(f"Error updating next billing date: {str(e)}")
