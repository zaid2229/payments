import frappe
from frappe import _
import stripe

@frappe.whitelist()
def get_header():
    stripe_settings = frappe.db.get_all('Stripe Settings',fields=['header_img'],filters={'is_default':1})
    print(f'\n\n\n\n{stripe_settings}')
    if stripe_settings[0].header_img:
        com_header = frappe.utils.get_url(stripe_settings[0].header_img)
        print(f'\n\n\n\n\n\n\n{com_header}\n\n\n\n\n\n\n\n\n\n\n')
    else:
        com_header = None
        
    return com_header

@frappe.whitelist(allow_guest=True)
def get_customer_id():
    user = frappe.session.user
    doctype = 'Sales Invoice'
    customers = []
    meta = frappe.get_meta(doctype)

    customer_field_name = get_customer_field_name(doctype)

    if meta.has_field(customer_field_name):
        if "Customer" in frappe.get_roles(user):
            customers = get_parents_for_user("Customer")
        elif frappe.has_permission(doctype, "read", user=user):
            customer_list = frappe.get_list("Customer")
            customers = [customer.name for customer in customer_list]
    
    if customers:

        stripe_details = frappe.db.get_all('Stripe Customers',fields=['name'],filters={'customer_name':customers[0]})

        print(stripe_details)
        
        return stripe_details[0].name

def get_customer_field_name(doctype):
	if doctype == "Quotation":
		return "party_name"
	else:
		return "customer"

def get_parents_for_user(parenttype: str) -> list[str]:
	portal_user = frappe.qb.DocType("Portal User")

	return (
		frappe.qb.from_(portal_user)
		.select(portal_user.parent)
		.where(portal_user.user == frappe.session.user)
		.where(portal_user.parenttype == parenttype)
	).run(pluck="name")


@frappe.whitelist(allow_guest=True)
def get_roles(uid):
    print(uid)

    print(frappe.get_roles(uid))

    return frappe.get_roles(uid)