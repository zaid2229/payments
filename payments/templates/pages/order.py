# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
import stripe


def get_context(context):
    stripe_settings = frappe.db.get_all("Stripe Settings", filters={'is_default':1})
    stripe_settings = frappe.get_doc("Stripe Settings", stripe_settings[0].name)
    stripe.api_key = stripe_settings.get_password(fieldname="secret_key", raise_exception=False)
    context.no_cache = 1
    context.show_sidebar = True
    context.doc = frappe.get_doc(frappe.form_dict.doctype, frappe.form_dict.name)
    invoice_no = context.doc.name
    if hasattr(context.doc, "set_indicator"):
        context.doc.set_indicator()

    context.parents = frappe.form_dict.parents
    context.title = frappe.form_dict.name
    context.payment_ref = frappe.db.get_value(
        "Payment Request", {"reference_name": frappe.form_dict.name}, "name"
    )

    default_print_format = frappe.db.get_value(
        "Property Setter",
        dict(property="default_print_format", doc_type=frappe.form_dict.doctype),
        "value",
    )
    if default_print_format:
        context.print_format = default_print_format
    else:
        context.print_format = "Standard"

    if not frappe.has_website_permission(context.doc):
        frappe.throw(_("Not Permitted"), frappe.PermissionError)

    context.available_loyalty_points = 0.0
    if context.doc.get("customer"):
        # check for the loyalty program of the customer
        customer_loyalty_program = frappe.db.get_value("Customer", context.doc.customer, "loyalty_program")

        if customer_loyalty_program:
            from erpnext.accounts.doctype.loyalty_program.loyalty_program import (
                get_loyalty_program_details_with_points,
            )

            loyalty_program_details = get_loyalty_program_details_with_points(
                context.doc.customer, customer_loyalty_program
            )
            context.available_loyalty_points = int(loyalty_program_details.get("loyalty_points"))

    context.show_pay_button = "payments" in frappe.get_installed_apps() and frappe.db.get_single_value(
        "Buying Settings", "show_pay_button"
    )
    context.show_make_pi_button = False
    if context.doc.get("supplier"):
        # show Make Purchase Invoice button based on permission
        context.show_make_pi_button = frappe.has_permission("Purchase Invoice", "create")
  
    context.show_subscription = False
    if context.doc.get("customer"):
            # Fetch Stripe customer record from ERPNext
            customer_name = context.doc.customer
            stripe_customer = frappe.db.get_all('Stripe Customers', fields=['customer_id', 'customer_name', 'email',"subscription_id"], filters={'customer_name': customer_name})
            
            print(stripe_customer)
            
            if stripe_customer:
                stripe_customer_id = stripe_customer[0].get("customer_id")
                context.stripe_customer_id = stripe_customer[0].get("customer_id")
                subscription_id = stripe_customer[0].get("subscription_id")


                context.is_attached_method = is_default_payment_method(stripe_customer_id)

                if stripe_customer_id:
                    context.show_subscription = True
                    print(context.stripe_customer_id)
                              
                    if subscription_id:
                        context.has_subscription = True
                        context.subscription_id = subscription_id
                        context.show_subscription = False
                        
                    else:
                        context.has_subscription = False

                
            
            # else:
            #     frappe.throw(_("Stripe Customer record not found for this ERPNext customer."), frappe.PermissionError)


            
        
def is_default_payment_method(customer_id):
    stripe_settings = frappe.db.get_all("Stripe Settings", filters={'is_default':1})
    stripe_settings = frappe.get_doc("Stripe Settings", stripe_settings[0].name)
        
    stripe.api_key = stripe_settings.get_password(fieldname="secret_key", raise_exception=False)
    customer = stripe.Customer.retrieve(customer_id)
    print(customer)
    if 'invoice_settings' in customer and 'default_payment_method' in customer['invoice_settings']:
        current_default_payment_method = customer['invoice_settings']['default_payment_method']
        
        print(current_default_payment_method)
        if current_default_payment_method:
            return True
        else:
            return False           
        
  
def get_attachments(dt, dn):
    return frappe.get_all(
        "File",
        fields=["name", "file_name", "file_url", "is_private"],
        filters={"attached_to_name": dn, "attached_to_doctype": dt, "is_private": 0},
    )



import stripe

@frappe.whitelist()
def get_setup_intent(customer_id):
    """
    Generate a SetupIntent for the provided Stripe customer ID.


    """
    try:

        url =frappe.utils.get_url()

        stripe_settings = frappe.db.get_all("Stripe Settings", filters={'is_default':1})
        stripe_settings = frappe.get_doc("Stripe Settings", stripe_settings[0].name)
        
        stripe.api_key = stripe_settings.get_password(fieldname="secret_key", raise_exception=False)

        # Create a SetupIntent for the customer
        setup_intent = stripe.SetupIntent.create(
            customer=customer_id,payment_method_types=["card",'us_bank_account'] # Specify ACH Direct Debit
        )


        return {
            "client_secret": setup_intent.client_secret,
            "setup_intent_id": setup_intent.id,
            "url":url
        }
    except Exception as e:
        frappe.throw(f"Error generating SetupIntent: {str(e)}")




@frappe.whitelist(allow_guest=True)
def create_stripe_billing_portal_session(customer_id,invoice_no):
    # Fetch your Stripe secret key
   
    stripe_settings = frappe.db.get_all("Stripe Settings", filters={'is_default':1})
    stripe_settings = frappe.get_doc("Stripe Settings", stripe_settings[0].name)
            
    stripe.api_key = stripe_settings.get_password(fieldname="secret_key", raise_exception=False) # Change to your actual settings doc


    url = frappe.utils.get_url()


    try:
        # Create a Stripe Billing Portal session for the customer
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{url}/invoices/{invoice_no}",  # Replace with the URL where you want the user to return after managing billing
        )
          
        # Return the session URL for redirection
        return session.url
    
    except Exception as e:
        frappe.log_error(f"Error creating Stripe billing portal session: {str(e)}", "Stripe Billing Portal Session Creation")
        raise


