$(document).ready(function () {

    var uid = frappe.session.user

    console.log(uid)

    var encodedEmail = encodeURIComponent(uid);
    console.log(encodedEmail)
    // Fetch user roles
    fetch(`/api/method/payments.templates.pages.pay-with-ach.get_roles?uid=${encodedEmail}`)
        .then(response => response.json())
        .then(data => {
            if (data.message && data.message.includes("Customer")) {
                // If user has "Customer" role, show Sales Invoice and Manage Billing

                var link = $('<div class="text-center"><a href="/invoices" id="sales-invoice-btn" class="col d-flex justify-content-center align-items-center btn btn-info text-white">Go to Invoices</a></div>');
                $(".row.account-info").append(link);
                
                

                // Create and append "Manage Billing" button
                var manageBillingBtn = $('<button id="manage-billing-btn" class="btn btn-primary" aria-label="Manage billing details">Manage Auto Pay</button>');
                $(".row.account-info").append(manageBillingBtn);

                // Attach event listener for Manage Billing button
                $("#manage-billing-btn").on("click", function () {
                    fetch('/api/method/payments.templates.pages.pay-with-ach.get_customer_id')
                        .then(response => response.json())
                        .then(data => {
                            if (data.message) {
                                return fetch(`/api/method/payments.templates.pages.order.create_stripe_billing_portal_session?customer_id=${data.message}`);
                            } else {
                                throw new Error("Customer ID not found");
                            }
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.message) {
                                window.location.href = data.message;
                            } else {
                                alert('Failed to create billing portal session');
                            }
                        })
                        .catch(error => {
                            console.error('Error:', error);
                            alert('An error occurred while opening the billing portal.');
                        });
                });
            }
        })
        .catch(error => {
            console.error('Error fetching user roles:', error);
        });
});
