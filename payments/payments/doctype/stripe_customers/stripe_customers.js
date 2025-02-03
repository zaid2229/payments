// Copyright (c) 2024, Standardtouch and contributors
// For license information, please see license.txt

frappe.ui.form.on("Stripe Customers", {

    refresh: function (frm) {
        frm.trigger('filter_invoices')
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


    },customer_name:function(frm){
        frm.trigger('filter_invoices')
        console.log('hiiiiiii')
    },
    day_of_month: function (frm) {
        if (frm.doc.day_of_month && frm.doc.interval !='day') {
            let day = frm.doc.day_of_month;
            let today = frappe.datetime.now_date(); // Get the current date
            let current_month = today.slice(0, 7);  // Extract "YYYY-MM" from the date
            
            // Construct the new anchor date in the format "YYYY-MM-DD"
            let new_anchor_date = `${current_month}-${String(day).padStart(2, '0')}`;
            
            // Check if the date is valid
            if (!frappe.datetime.validate(new_anchor_date)) {
                frappe.msgprint(__('Invalid day! Please enter a valid day in the current month.'));
                frm.set_value('anchor_date', null); // Clear anchor date if invalid
                return;
            }
            
            // Update the Anchor Date field
            frm.set_value('anchor_date', new_anchor_date);
        }
    },
    filter_invoices: function (frm) {
        if (frm.doc.customer_name) {
            frm.set_query('invoice', function () {
                return {
                    filters: {
                        customer: frm.doc.customer_name,
                        status: ['not in', ['Not Paid', 'Draft','Cancelled']],
                        custom_is_billing_invoice:1
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
