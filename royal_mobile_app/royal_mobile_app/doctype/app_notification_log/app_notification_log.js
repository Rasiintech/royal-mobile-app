// Copyright (c) 2025, rasiin and contributors
// For license information, please see license.txt

frappe.ui.form.on('App Notification Log', {
    refresh: function(frm) {
        // Add send button for manual retry
        if (frm.doc.status === 'Failed') {
            frm.add_custom_button(__('Retry'), () => {
                frappe.call({
                    method: 'medical_app.services.notification_service.retry_notification',
                    args: { name: frm.doc.name },
                    callback: (r) => {
                        if (r.message && r.message.success) {
                            frappe.show_alert({
                                message: __('Notification resent successfully'),
                                indicator: 'green'
                            });
                        } else {
                            frappe.show_alert({
                                message: __('Retry failed: {0}', [r.message.message || 'Unknown error']),
                                indicator: 'red'
                            });
                        }
                        frm.reload_doc();
                    },
                    freeze: true,
                    freeze_message: __('Retrying notification...')
                });
            }).addClass('btn-primary');
        }

        // Add topic management buttons for push notifications with valid recipients
        // if (frm.doc.type === 'Push Notification' && this.hasValidRecipients(frm)) {
            frm.add_custom_button(__('Subscribe to Topic'), () => {
                this.show_topic_dialog(frm, 'subscribe');
            }).addClass('btn-default');

            frm.add_custom_button(__('Unsubscribe from Topic'), () => {
                this.show_topic_dialog(frm, 'unsubscribe');
            }).addClass('btn-default');
        // }
    },

    hasValidRecipients: function(frm) {
        // Check if this is a push notification with identifiable recipients
        if (frm.doc.type !== 'Push Notification') return false;
        
        // Check different recipient types
        switch(frm.doc.recipient_type) {
            case 'Single User':
                return !!frm.doc.user;
            case 'Single Patient':
                return !!frm.doc.patient;
            case 'Multiple Users':
                return frm.doc.selected_users && frm.doc.selected_users.length > 0;
            case 'Multiple Patients':
                return frm.doc.selected_patients && frm.doc.selected_patients.length > 0;
            case 'All Users':
            case 'All Patients':
                return true;
            default:
                return false;
        }
    },

    show_topic_dialog: function(frm, operation) {
        const dialog = new frappe.ui.Dialog({
            title: __(operation === 'subscribe' ? 'Subscribe to Topic' : 'Unsubscribe from Topic'),
            fields: [
                {
                    label: __('Topic Name'),
                    fieldname: 'topic',
                    fieldtype: 'Data',
                    reqd: 1,
                    description: __('Enter the topic name to ' + 
                        (operation === 'subscribe' ? 'subscribe to' : 'unsubscribe from'))
                }
            ],
            primary_action_label: __(operation === 'subscribe' ? 'Subscribe' : 'Unsubscribe'),
            primary_action: function() {
                const values = dialog.get_values();
                if (values) {
                    frappe.call({
                        method: 'medical_app.services.notification_service.manage_topic_subscription',
                        args: {
                            notification_log_name: frm.doc.name,
                            topic: values.topic,
                            operation: operation
                        },
                        callback: function(r) {
                            if (!r.exc) {
                                frappe.show_alert({
                                    message: __(operation === 'subscribe' ? 
                                        'Successfully subscribed to topic {0}' : 
                                        'Successfully unsubscribed from topic {0}', 
                                        [values.topic]),
                                    indicator: 'green'
                                });
                            }
                            dialog.hide();
                        },
                        freeze: true,
                        freeze_message: __(operation === 'subscribe' ? 
                            'Subscribing to topic...' : 'Unsubscribing from topic...')
                    });
                }
            }
        });
        
        dialog.show();
    }
});