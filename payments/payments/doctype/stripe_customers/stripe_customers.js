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
    day_of_month: function(frm) {
        if (frm.doc.day_of_month && frm.doc.interval != 'day') {
            let day = frm.doc.day_of_month;
            let today = frappe.datetime.now_date(); // Get the current date
            let current_month = today.slice(0, 7);  // Extract "YYYY-MM" from the date
            let current_year = today.slice(0, 4);
            let current_month_number = parseInt(today.slice(5, 7), 10);
            let today_day = parseInt(today.slice(8, 10), 10); // Get today's day of the month
            
            // Get the number of days in the current month using JavaScript's Date object
            let next_month = current_month_number === 12 ? 1 : current_month_number + 1;
            let next_month_year = current_month_number === 12 ? (parseInt(current_year) + 1) : current_year;
            let last_day_of_current_month = new Date(next_month_year, next_month, 0).getDate(); // Last day of the current month
            
            // If the day provided is greater than the days in the current month, set anchor date to next month
            if (day > last_day_of_current_month) {
                let new_anchor_date = `${next_month_year}-${String(next_month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                frm.set_value('anchor_date', new_anchor_date);
            } else {
                // Check if the selected day has already passed this month
                let new_anchor_date;
                if (day < today_day) {
                    // If the selected day has already passed, set the anchor date to the same day next month
                    new_anchor_date = `${next_month_year}-${String(next_month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                } else {
                    // Otherwise, set the anchor date in the current month
                    new_anchor_date = `${current_month}-${String(day).padStart(2, '0')}`;
                }
    
                // Check if the constructed date is valid in the current month
                let date_check = new Date(`${current_month}-${String(day).padStart(2, '0')}`);
                if (date_check.getDate() !== day) {
                    frappe.msgprint(__('Invalid day! Please enter a valid day in the current month.'));
                    frm.set_value('anchor_date', null); // Clear anchor date if invalid
                    return;
                }
    
                // Update the Anchor Date field
                frm.set_value('anchor_date', new_anchor_date);
            }
        }
    }
    ,
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
