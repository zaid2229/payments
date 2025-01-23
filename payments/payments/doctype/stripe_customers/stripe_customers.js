// Copyright (c) 2024, Standardtouch and contributors
// For license information, please see license.txt

frappe.ui.form.on("Stripe Customers", {

    refresh: function (frm) {
        if (frm.doc.customer_id ) {
            frm.add_custom_button(__('Send Email'), function () {
                frappe.call({
                    method: "payments.payments.doctype.stripe_customers.stripe_customers.invoice_subscription_notification",
                    args: {
                        name: frm.doc.name,
                    },
                    callback: function(response) {
                        if (response.message=='success') {
                            frappe.msgprint(__('Email Sent Successfully!'));
                        }
                    }
                });
            });
            if(frm.doc.subscription_status ==='Active' )
            frm.add_custom_button(__('Cancel Subscription'), function () {
                frappe.call({
                    method: "payments.payments.doctype.stripe_customers.stripe_customers.cancel_subscription",
                    args: {
                        "subscription_id": frm.doc.subscription_id
                    },
                    callback: function (response) {
                        if (response.message.error) {
                            frappe.msgprint(response.message.error);
                        } else {
                            frm.set_value('subscription_status', 'Cancelled')
                            frm.save(
                            )
                            console.log(response.message)

                            frappe.msgprint("Payment method collection initiated. Please check your email.");
                        }
                    }
                });
            });
        }


    },
    customer_name: function (frm) {
        if (frm.doc.customer_name) {
            frm.set_query('invoice', function () {
                return {
                    filters: {
                        customer: frm.doc.customer_name,
                        status: ['not in', ['Not Paid', 'Draft','Cancelled']]
                    }
                };
            });
        } else {
            frm.set_query('invoice', function () {
                return {};
            });
        }
    }
});
