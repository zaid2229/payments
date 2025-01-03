# Copyright (c) 2024, Standardtouch and contributors
# For license information, please see license.txt
import frappe
from frappe.model.document import Document
import stripe

from frappe import utils



stripe_settings = frappe.get_doc("Stripe Settings", 'Bayaan Test Mode')
stripe.api_key = stripe_settings.get_password(fieldname="secret_key", raise_exception=False)

class StripeCustomers(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from bayan_erp.bayan_erp.doctype.subscription_items.subscription_items import SubscriptionItems
		from frappe.types import DF

		billing_date: DF.Date | None
		customer_id: DF.Data | None
		customer_mandate_status: DF.Literal["Pending", "Accepted"]
		customer_name: DF.Link | None
		default_payment_method_id: DF.Data | None
		email: DF.Data | None
		invoice: DF.Link | None
		next_billing_date: DF.Date | None
		subscription_id: DF.Data | None
		subscription_items: DF.Table[SubscriptionItems]
		subscription_status: DF.Literal["Pending", "Active", "Cancelled"]
	# end: auto-generated types

	
	def before_insert(self):
		self.create_stripe_customer()

	def create_stripe_customer(self):
		"""
		This function is called when a new Stripe Customer is created.
		It creates a customer in Stripe and saves the Stripe Customer ID in ERPNext.
		"""
		try:
			# Create a customer in Stripe using the email and name from the ERPNext DocType
			stripe_customer = stripe.Customer.create(
				email=self.email,
				name=self.customer_name
			)

			# Store the Stripe Customer ID in the DocType
			self.customer_id = stripe_customer.id

			# Optionally, you can log or send an email about the creation
			frappe.msgprint(f"Stripe customer {stripe_customer.id} created successfully.")

		except stripe.error.StripeError as e:
			frappe.throw(f"Stripe API Error: {str(e)}")
		except Exception as e:
			frappe.throw(f"Error creating Stripe customer: {str(e)}")


@frappe.whitelist()
def create_payment_intent_for_ach(docname):
    """
    Creates a PaymentIntent for ACH Direct Debit and returns the client secret to the client-side.
    """
    doc = frappe.get_doc("Stripe Customers", docname)

    try:
        # Create a PaymentIntent for ACH Direct Debit
        payment_intent = stripe.PaymentIntent.create(
            amount=2000,  # Example: amount in cents
            currency="usd",
            payment_method_types=["us_bank_account"],
            customer=doc.customer_id,
            capture_method="automatic",
        )
        
        print(payment_intent.client_secret)

        # Return the client secret for the frontend to complete the payment
        send_payment_email(doc, payment_intent['client_secret'])
        return payment_intent.client_secret

    except stripe.error.StripeError as e:
        frappe.throw(f"Error creating Payment Intent: {str(e)}")
        



@frappe.whitelist(allow_guest=True)
def create_stripe_subscription_for_invoice(customer_id, invoice_id):
    # Fetch Stripe Settings
    
    stripe_settings = frappe.get_doc("Stripe Settings", 'Bayaan Test Mode')
    stripe.api_key = stripe_settings.get_password(fieldname="secret_key", raise_exception=False)

    price_ids = []
    
    # Get customer and invoice details
    stripe_details = frappe.get_doc('Stripe Customers', customer_id)
    invoice = frappe.get_doc("Sales Invoice", invoice_id)

    try:
        # Fetch the customer's payment methods
        response = stripe.PaymentMethod.list(
            customer=customer_id,  # Correctly pass customer_id  # Fetch only card types (can be adjusted if needed)
        )
        
        # Check if there is at least one payment method
        if response['data']: 
            first_payment_method_id = response['data'][0]['id']
            print(f"First Payment Method ID: {first_payment_method_id}")
        else:
            raise Exception(f"No payment methods found for customer {customer_id}")
        
        # Fetch the current default payment method for the customer
        customer = stripe.Customer.retrieve(customer_id)

        if 'invoice_settings' in customer and 'default_payment_method' in customer['invoice_settings']:
            current_default_payment_method = customer['invoice_settings']['default_payment_method']
            print(f"Current default payment method: {current_default_payment_method}")

            # If the current default payment method is not set or is different from the one fetched above, attach the new one
            if not current_default_payment_method or current_default_payment_method != first_payment_method_id:
                # Attach the new payment method as the default payment method
                stripe.Customer.modify(
                    customer_id,
                    invoice_settings={"default_payment_method": first_payment_method_id}
                )
                print(f"Attached Payment Method {first_payment_method_id} to customer {customer_id}")
        else:
            # If no default payment method is set, attach the first payment method
            stripe.Customer.modify(
                customer_id,
                invoice_settings={"default_payment_method": first_payment_method_id}
            )

            stripe_details.default_payment_method_id = first_payment_method_id
            stripe_details.save(ignore_permissions=True)
            print(f"Attached Payment Method {first_payment_method_id} to customer {customer_id}")

    except Exception as e:
        frappe.log_error(f"Error fetching and attaching payment methods for customer {customer_id}: {str(e)}", "Stripe Payment Methods")
        raise

    try:
        # Step 1: Create a Product and Price for each item in the invoice
        for item in invoice.items:
            for stripeitem in stripe_details.subscription_items:
                student_name = item.item_name
                rate = item.rate  # Assuming rate is the subscription amount

                # Step 2: Create a Product in Stripe
                product = stripe.Product.create(
                    name=student_name,
                    description=f"Subscription for {student_name}",
                )

                # Step 3: Create a Price for the Product
                price = stripe.Price.create(
                    unit_amount=int(rate * 100),  # Convert rate to cents
                    currency='usd',  # Assuming USD as the currency
                    recurring={"interval": "month"},  # Monthly subscription
                    product=product['id'],
                )

                

                stripeitem.product_id = product['id']
                stripeitem.stripe_price_id=price['id']
                stripe_details.save(ignore_permissions=True)

                print(f"Created price for product: {price}")

                price_ids.append({'price': price['id']})  # Append each price object in a list to use in subscription

    except Exception as e:
        frappe.log_error(f"Error in creating Stripe products and prices for invoice {invoice_id}: {str(e)}", "Stripe Subscription Creation")
        raise

    try:
        # Step 4: Create Subscription
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=price_ids,  # Attach all price items to the subscription  # Handle incomplete payments
            expand=['latest_invoice.payment_intent'],  # Expanding the payment intent for further processing
        )

        print(f"Created Subscription: {subscription.id}")

        # Save subscription details in the Stripe Customers document
        frappe.db.set_value('Stripe Customers', customer_id, 'subscription_id', subscription.id)
        frappe.db.set_value('Stripe Customers', customer_id, 'subscription_status', 'Active')
        frappe.db.set_value('Stripe Customers',customer_id,'billing_date',frappe.utils.nowdate())
        frappe.db.commit()

        # Log and return the subscription details
        frappe.log_error(f"Subscription Created: {subscription.id}", "Stripe Subscription Creation")
        return subscription

    except Exception as e:
        frappe.log_error(f"Error in creating Stripe subscription for invoice {invoice_id}: {str(e)}", "Stripe Subscription Creation")
        raise



@frappe.whitelist()
def send_payment_email(customer_email, invoice_id):
    """
    Sends an email to the customer with the link to complete their ACH payment mandate.
    """
    # Construct the URL to complete ACH mandate

    site_url = frappe.utils.get_url()
    payment_url = f"{site_url}/invoices/{invoice_id}"


    # Prepare email message
    subject = "Complete Your ACH Mandate for Subscription"
    message = f"""
    Dear Customer,

    You have initiated a subscription with us. To complete your payment process, please click the link below to confirm your ACH payment mandate.

    {payment_url}

    Once confirmed, we will activate your subscription and start billing.

    Thank you,
    Your Company Name
    """

    # Send email via ERPNext's email service
    frappe.sendmail(
        recipients=[customer_email],
        subject=subject,
        message=message
    )


@frappe.whitelist()
def check_subscription_status(customer_id, invoice_id):
    subscription = frappe.get_all("Stripe Customers", 
        filters={
            "customer_id": customer_id, 
            "invoice": invoice_id,
            "subscription_status": "Active"
        }, 
        fields=["subscription_status"]
    )
    if subscription:
        return {"status": "active"}
    return {"status": "inactive"}

@frappe.whitelist()
def cancel_subscription(subscription_id):
    response = stripe.Subscription.delete(subscription_id)
    return response