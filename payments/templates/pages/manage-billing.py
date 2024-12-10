import frappe
from frappe import _


def get_context(context):
    context.no_cache = 1
    context.show_sidebar = True
    context.doc = frappe.get_doc(frappe.form_dict.doctype, frappe.form_dict.name)
    print(context.doc)