# Copyright (c) 2024, Standardtouch and contributors
# For license information, please see license.txt
import frappe
from frappe.model.document import Document
import stripe

from frappe import utils
import datetime




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
		self.set_stripe_id()
		
	def set_stripe_id(self):
		frappe.db.set_value('Customer',self.customer_name,'custom_stripe_id',self.customer_id)
		frappe.db.set_value('Sales Invoice',self.customer_name,'custom_stripe_id',self.customer_id)
		frappe.db.commit()

	def create_stripe_customer(self):
		stripe_settings = frappe.db.get_all("Stripe Settings", filters={'is_default':1})
		stripe_settings = frappe.get_doc("Stripe Settings", stripe_settings[0].name)
		stripe.api_key = stripe_settings.get_password(fieldname="secret_key", raise_exception=False)
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
	stripe_settings = frappe.db.get_all("Stripe Settings", filters={'is_default':1})
	stripe_settings = frappe.get_doc("Stripe Settings", stripe_settings[0].name)
	stripe.api_key = stripe_settings.get_password(fieldname="secret_key", raise_exception=False)
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
		
		send_payment_email(doc, payment_intent['client_secret'])
		return payment_intent.client_secret

	except stripe.error.StripeError as e:
		frappe.throw(f"Error creating Payment Intent: {str(e)}")
		



@frappe.whitelist(allow_guest=True)
def create_stripe_subscription_for_invoice(customer_id, invoice_id):

	stripe_settings = frappe.db.get_all("Stripe Settings", filters={'is_default':1})
	stripe_settings = frappe.get_doc("Stripe Settings", stripe_settings[0].name)
	stripe.api_key = stripe_settings.get_password(fieldname="secret_key", raise_exception=False)
	customer_stripe_interval = frappe.db.get_value("Stripe Customers",customer_id,'interval')


	price_ids = []
	
	# Get customer and invoice details
	stripe_details = frappe.get_doc('Stripe Customers', customer_id)
	
	anchor_date= stripe_details.anchor_date
	end_date = stripe_details.auto_pay_end_date
	if isinstance(end_date, datetime.date):
		end_date = end_date.strftime("%Y-%m-%d")

	if anchor_date:
		if isinstance(anchor_date, datetime.date):
			anchor_date = anchor_date.strftime("%Y-%m-%d")
		anchor_date = int(datetime.datetime.strptime(anchor_date, "%Y-%m-%d").timestamp())


	invoice = frappe.get_doc("Sales Invoice", invoice_id)

	end_date = int(datetime.datetime.strptime(end_date, "%Y-%m-%d").timestamp())

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

			# If the current default payment method is not set or is different from the one fetched above, attach the new one
			if not current_default_payment_method or current_default_payment_method != first_payment_method_id:
				# Attach the new payment method as the default payment method
				stripe.Customer.modify(
					customer_id,
					invoice_settings={"default_payment_method": first_payment_method_id}
				)
		else:
			# If no default payment method is set, attach the first payment method
			stripe.Customer.modify(
				customer_id,
				invoice_settings={"default_payment_method": first_payment_method_id}
			)

			stripe_details.default_payment_method_id = first_payment_method_id
			stripe_details.save(ignore_permissions=True)

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
					recurring={"interval": customer_stripe_interval},  # Monthly subscription
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
		if stripe_details.interval == 'day':
			subscription = stripe.Subscription.create(
				customer=customer_id,
				items=price_ids,  # Attach all price items to the subscription  # Handle incomplete payments
				expand=['latest_invoice.payment_intent'],  
				cancel_at=end_date
			)

		else:
			subscription = stripe.Subscription.create(
				customer=customer_id,
				items=price_ids,  # Attach all price items to the subscription  # Handle incomplete payments
				expand=['latest_invoice.payment_intent'],
				billing_cycle_anchor=anchor_date,  
				cancel_at=end_date
			)

		subscription_start_date = frappe.utils.nowdate()

		# Extract next payment date from the subscription (e.g., current_period_end)
		next_payment_date = subscription.get("current_period_end")  # Unix timestamp from Stripe
		next_payment_date = frappe.utils.datetime.datetime.fromtimestamp(next_payment_date).date()  # Convert to date

		# Calculate Repeat on Day (day before the subscription date)
		repeat_on_day = next_payment_date.day - 1  # Set to one day before the subscription date

		# Handle edge case: If day becomes zero (1st of the month), set to the last day of the previous month
		if repeat_on_day == 0:
			previous_month = frappe.utils.add_months(next_payment_date, -1)
			repeat_on_day = frappe.utils.get_last_day(previous_month).day

			# Determine the frequency for Auto Repeat based on the subscription interval
		if customer_stripe_interval == 'month':
			frequency = 'Monthly'
		elif customer_stripe_interval == 'day':
			frequency = 'Daily'
		else:
			frequency = 'Yearly'

		invoice_repeat = frappe.new_doc('Auto Repeat')
		invoice_repeat.reference_doctype = 'Sales Invoice'
		invoice_repeat.reference_document = invoice_id
		invoice_repeat.start_date = subscription_start_date  # Start on subscription date
		invoice_repeat.end_date = stripe_details.auto_pay_end_date
		invoice_repeat.frequency = frequency  # Assuming monthly subscription
		invoice_repeat.repeat_on_day = repeat_on_day  # Repeat on the day before the subscription payment date
		# invoice_repeat.create_draft = 1  # Creates draft invoices for review
		invoice_repeat.submit_on_creation = 1  # Automatically submits invoices (optional)
		invoice_repeat.save(ignore_permissions=True)

		# Save subscription details in the Stripe Customers document
		frappe.db.set_value('Stripe Customers', customer_id, 'subscription_id', subscription.id)
		frappe.db.set_value('Stripe Customers', customer_id, 'subscription_status', 'Active')
		frappe.db.set_value('Stripe Customers',customer_id,'billing_date',subscription_start_date)
		# frappe.db.set_value('Stripe Customers',customer_id,'billing_date',frappe.utils.nowdate())
		frappe.db.commit()

		return subscription

	except Exception as e:
		frappe.log_error(f"Error in creating Stripe subscription for invoice {invoice_id}: {str(e)}", "Stripe Subscription Creation")
		raise

@frappe.whitelist(allow_guest=True)
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

@frappe.whitelist(allow_guest=True)
def cancel_subscription(subscription_id):
	stripe_settings = frappe.db.get_all("Stripe Settings", filters={'is_default':1})
	stripe_settings = frappe.get_doc("Stripe Settings", stripe_settings[0].name)
	stripe.api_key = stripe_settings.get_password(fieldname="secret_key", raise_exception=False)
	response = stripe.Subscription.delete(subscription_id)
	return response

import frappe
from frappe.utils.file_manager import save_file
from frappe.core.doctype.communication.email import make
from frappe import render_template

@frappe.whitelist(allow_guest=True)
def invoice_subscription_notification(name):
	try:
		# Fetch Stripe Customer Document
		stripe_customer = frappe.get_doc("Stripe Customers", name)

		# Get the linked ERPNext Invoice
		if not stripe_customer.invoice:
			return "No ERPNext Invoice linked to this customer."

		invoice_name = stripe_customer.invoice
		invoice = frappe.get_doc("Sales Invoice", invoice_name)

		default_print_format = frappe.db.get_value("Property Setter", {"doc_type": "Sales Invoice", "property": "default_print_format"}, "value") or "Standard"

		frappe.logger().info(f"Using Print Format: {default_print_format}")

		# ✅ Attach Invoice as a Print Format PDF
		my_attachments = [frappe.attach_print(
			doctype="Sales Invoice",
			name=invoice_name,
			print_format=default_print_format,
			file_name=f"{invoice_name}.pdf"
		)]

		# Debugging: Check if the PDF is properly attached
		frappe.logger().info(f"Generated Attachments: {my_attachments}")

		# Prepare email content using an Email Template
		email_template = frappe.get_doc("Email Template", "Auto Pay Invoice Email")


		email_body = frappe.render_template(email_template.response_html, {
			"customer_name": stripe_customer.customer_name,
			"invoice": invoice_name
		})


		print(email_body)

		subject = f"Set Up Auto-Pay for Invoice {invoice_name}"

		frappe.sendmail(
			recipients=[stripe_customer.email],  # Ensure the email field exists
			sender='accounts@bayaanacademy.com',
			subject=subject,
			message=email_body,
			reference_doctype="Sales Invoice",
			reference_name=invoice_name,
			attachments=my_attachments
		)

		return "success"

	except Exception as e:
		frappe.log_error(message=str(e), title="Invoice Subscription Notification Error")

