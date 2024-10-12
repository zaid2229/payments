# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE
import json

import frappe
from frappe import _
from frappe.utils import cint, fmt_money

from payments.payment_gateways.doctype.stripe_settings.stripe_settings import (
	get_gateway_controller,
)

no_cache = 1

expected_keys = (
	"amount",
	"title",
	"description",
	"reference_doctype",
	"reference_docname",
	"payer_name",
	"payer_email",
	"order_id",
	"currency",
)


def get_context(context):
	context.no_cache = 1

	# all these keys exist in form_dict
	if not (set(expected_keys) - set(list(frappe.form_dict))):
		for key in expected_keys:
			context[key] = frappe.form_dict[key]

		gateway_controller = get_gateway_controller(context.reference_doctype, context.reference_docname)
		context.publishable_key = get_api_key(context.reference_docname, gateway_controller)
		context.image = get_header_image(context.reference_docname, gateway_controller)

		context["amount"] = fmt_money(amount=context["amount"], currency=context["currency"])

		if is_a_subscription(context.reference_doctype, context.reference_docname):
			payment_plan = frappe.db.get_value(
				context.reference_doctype, context.reference_docname, "payment_plan"
			)
			recurrence = frappe.db.get_value("Payment Plan", payment_plan, "recurrence")

			context["amount"] = context["amount"] + " " + _(recurrence)

	else:
		frappe.redirect_to_message(
			_("Some information is missing"),
			_("Looks like someone sent you to an incomplete URL. Please ask them to look into it."),
		)
		frappe.local.flags.redirect_location = frappe.local.response.location
		raise frappe.Redirect


def get_api_key(doc, gateway_controller):
	publishable_key = frappe.db.get_value("Stripe Settings", gateway_controller, "publishable_key")
	if cint(frappe.form_dict.get("use_sandbox")):
		publishable_key = frappe.conf.sandbox_publishable_key

	return publishable_key


def get_header_image(doc, gateway_controller):
	header_image = frappe.db.get_value("Stripe Settings", gateway_controller, "header_img")

	return header_image


@frappe.whitelist(allow_guest=True)
def make_payment(stripe_token_id, data, reference_doctype=None, reference_docname=None):
	data = json.loads(data)

	data.update({"stripe_token_id": stripe_token_id})

	gateway_controller = get_gateway_controller(reference_doctype, reference_docname)
	payment_entry(stripe_token_id, data,reference_doctype,reference_docname)

	if is_a_subscription(reference_doctype, reference_docname):
		reference = frappe.get_doc(reference_doctype, reference_docname)
		data = reference.create_subscription("stripe", gateway_controller, data)
	else:
		data = frappe.get_doc("Stripe Settings", gateway_controller).create_request(data)

	frappe.db.commit()
	return data


def is_a_subscription(reference_doctype, reference_docname):
	if not frappe.get_meta(reference_doctype).has_field("is_a_subscription"):
		return False
	return frappe.db.get_value(reference_doctype, reference_docname, "is_a_subscription")



import frappe
from frappe.utils import flt, nowdate

@frappe.whitelist(allow_guest=True)
def payment_entry(stripe_token_id, data, reference_doctype, reference_docname):
    try:
        # Fetch the Sales Invoice document
        invoice = frappe.get_doc(reference_doctype, reference_docname)

        # Get outstanding amount for the invoice in transaction currency
        outstanding_amount = invoice.grand_total 
        transaction_currency = invoice.currency  # Example: USD

        # Company base currency (e.g., INR)
        company_currency = frappe.get_value("Company", invoice.company, "default_currency")

        # Get the current exchange rate between transaction currency and company currency
        exchange_rate = get_exchange_rate(transaction_currency, company_currency)

        # Calculate amounts in account (company) currency
        debit_amount_in_account_currency = flt(outstanding_amount) * flt(exchange_rate)

        # Fetch the required accounts (for debiting and crediting)
        receivable_account = frappe.get_value("Company", invoice.company, "default_receivable_account")
        bank_account = frappe.get_value("Company", invoice.company, "default_bank_account")

        # Prepare GL Entries for both transaction and account currencies
        gl_entries = [
            {
                "account": receivable_account,
                "party_type": "Customer",
                "party": invoice.party,
                "debit": flt(outstanding_amount),  # Debit in Transaction Currency (e.g., USD)
                "debit_in_account_currency": flt(debit_amount_in_account_currency),  # Debit in Account Currency (e.g., INR)
                "credit": 0,
                "credit_in_account_currency": 0,
                "voucher_type": "Sales Invoice",
                "voucher_no": invoice.reference_name,
                "company": invoice.company,
                "posting_date": nowdate(),
                "against": bank_account,
                "remarks": "Payment received via Stripe",
                "debit_in_transaction_currency": outstanding_amount,  # Debit in Transaction Currency
                "credit_in_transaction_currency": 0  # No credit in transaction currency here
            },
            {
                "account": bank_account,
                "debit": 0,
                "debit_in_account_currency": 0,
                "credit": flt(outstanding_amount),  # Credit in Transaction Currency (e.g., USD)
                "credit_in_account_currency": flt(debit_amount_in_account_currency),  # Credit in Account Currency (e.g., INR)
                "voucher_type": "Sales Invoice",
                "voucher_no": invoice.reference_name,
                "company": invoice.company,
                "posting_date": nowdate(),
                "against": receivable_account,
                "remarks": "Payment received via Stripe",
                "debit_in_transaction_currency": 0,  # No debit in transaction currency here
                "credit_in_transaction_currency": outstanding_amount  # Credit in Transaction Currency
            }
        ]

        # Insert GL entries
        for entry in gl_entries:
            gl_entry = frappe.get_doc({
                "doctype": "GL Entry",
                **entry
            })
            gl_entry.insert(ignore_permissions=True)
            gl_entry.submit()

        # Mark the Sales Invoice as Paid
        frappe.db.set_value("Sales Invoice", invoice.reference_name, "status", "Paid")
        frappe.db.set_value("Sales Invoice", invoice.reference_name, "outstanding_amount", outstanding_amount)

        # Commit changes to DB
        frappe.db.commit()


    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Direct GL Entry Payment Failed")
        return {
            "status": "Failed",
            "error": str(e),
            "redirect_to": "/desk#Form/Sales Invoice/{}".format(reference_docname)
        }

def get_exchange_rate(from_currency, to_currency):
    """Utility function to get the exchange rate between two currencies."""
    return frappe.db.get_value("Currency Exchange", {
        "from_currency": from_currency,
        "to_currency": to_currency
    }, "exchange_rate") or 1.0  # Default to 1 if no rate found
