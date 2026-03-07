# Copyright (c) 2025, rasiin and contributors
# For license information, please see license.txt

import frappe
import json
import re
from frappe.model.document import Document
from medical_app.services.notification_service import NotificationService

class AppNotificationLog(Document):
    def before_save(self):
        """Set default status"""
        if self.is_new():
            self.status = "Pending"

    def after_insert(self):
        """Trigger notification sending after insert"""
        self.send_notification()

    def send_notification(self):
        """Send the notification based on type"""
        try:
            service = NotificationService(app_target=self.app_target)
            
            # Remove The Htm Content
            plain_message = re.sub(r"<[^>]+>", "", self.message or "")
            
            # Determine image source (URL or file)
            image_source = self.image_url or self.image_file
            
            doc_data = self.as_dict()
            doc_data["message"] = plain_message
            doc_data["image"] = image_source
            
            result = service.send_notification(doc_data)

            # Update status and response
            self.status = "Sent" if result.get("success") else "Failed"
            self.api_response = json.dumps(result)
            self.sent_on = frappe.utils.now()
            self.delivered_on = frappe.utils.now()
            
             # Save but don't trigger hooks    
            self.db_update()
        except Exception as e:
            frappe.log_error("Notification Send Failed", str(e))
            self.status = "Failed"
            self.api_response = json.dumps({"error": str(e)})
            self.db_update()
