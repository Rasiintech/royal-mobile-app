// Add Dashboard link to Sidebar


// frappe.ready(() => {
//     frappe.provide("frappe.ui");
    
//     frappe.ui.Sidebar.add_item({
//         type: 'link',
//         label: __('Feedback Analytics'),
//         route: '/dashboard-view/Patient Feedback Analytics',
//         group: __('Healthcare'),
//         icon: 'fa fa-chart-bar',
//         order: 10
//     });
// });


// Updated patient_feedback_sidebar.js
frappe.provide("frappe.ui");

// Use document.ready instead of frappe.ready
$(document).on('frappe-ready', function() {
    if(frappe.user.has_role('Healthcare Administrator') || 
       frappe.user.has_role('System Manager')) {
        
        frappe.ui.Sidebar.add_item({
            type: 'link',
            label: __('Feedback Analytics'),
            route: '/dashboard-view/Patient%20Feedback%20Analytics',
            group: __('Healthcare'),
            icon: 'fa fa-chart-bar',
            order: 10
        });
    }
});