import frappe
from frappe import _

@frappe.whitelist()
def get_sales_invoices():
    """Get sales invoices based on user permissions"""
    fields = ['name', 'custom_invoice_month', 'status', 'customer', 'grand_total']
    filters = {'docstatus': 1}  # Only fetch submitted invoices (docstatus=1)

    # Step 1: Check if the logged-in user is a Guest or Admin
    if frappe.session.user != 'Guest' and not frappe.session.user.startswith('Administrator'):
        user_type = frappe.db.get_value('User', frappe.session.user, 'user_type')
        roles = frappe.get_roles(frappe.session.user)

        # Step 2: Apply filtering for users with the Customer role only
        if user_type in ['Website User','System User'] and 'Customer' in roles:
            # Step 3: Get the email of the logged-in user from the User Doctype
            email = frappe.db.get_value('User', frappe.session.user, 'email')

            if email:
                # Step 4: Find the customer linked to this email in Portal User
                customer = frappe.db.get_value('Portal User', {'user': email}, 'parent')

                if customer:
                    filters['customer'] = customer  # Step 5: Filter invoices by Customer

    # Step 6: Fetch and return the list of invoices
    return frappe.get_list('Sales Invoice', fields=fields, filters=filters)

def get_context(context):
    """Get context for the sales invoice list webpage"""
    context.no_cache = 1
    context.show_sidebar = True
    context.title = _("Sales Invoices")
    context.invoices = get_sales_invoices()
