# frappe-bench/apps/royal_mobile_app/royal_mobile_app/services/notification_service.py

from typing import Dict, List, Optional, Union
import frappe
import re
import json
from frappe.utils.background_jobs import enqueue
from .fcm_service import FCMService
from .hormuud_sms_service import HormuudSMSService

class NotificationService:
    SOMALI_PHONE_REGEX = r'^(\+252|252|0)?[67]\d{7}$'

    
    def __init__(self, app_target: str = None):
        """
        Initialize with target app
        Args:
            app_target: "Medical App" or "Haldoor App" - determines FCM config
        """
        self.app_target = app_target
        self.fcm = FCMService(app_name=app_target)
        self.sms = HormuudSMSService()

    def send_notification(self, doc_dict: Dict) -> Dict:
        """
        Main method to handle all notification types
        Args:
            doc_dict: Dictionary with notification details (matches App Notification Log fields)
        Returns:
            Dict with send results
        """
        try:
            self._validate_notification(doc_dict)
            
            if doc_dict.get("type") == "SMS":
                result = self._send_sms_notification(doc_dict)
            else:
                result = self._send_push_notification(doc_dict)
            
            self._update_notification_log(doc_dict, result)
            return result
            
        except Exception as e:
            frappe.log_error("Notification Failed", str(e))
            result = {"success": False, "error": str(e)}
            self._update_notification_log(doc_dict, result)
            return result


    def _validate_notification(self, doc_dict: Dict):
        """Validate notification parameters"""
        if not doc_dict.get("message"):
            frappe.throw("Message content is required")
            
        if doc_dict.get("type") == "SMS":
            if not doc_dict.get("subject"):
                frappe.throw("SMS subject is required")
        elif doc_dict.get("type") == "Push Notification":
            if not doc_dict.get("title"):
                frappe.throw("Notification title is required")

    def _update_notification_log(self, doc_dict: Dict, result: Dict):
        """Update the notification log with results"""
        if not doc_dict.get("name"):
            return
            
        status = "Sent" if result.get("success") else "Failed"
        frappe.db.set_value("App Notification Log", doc_dict["name"], {
            "status": status,
            "api_response": json.dumps(result),
            "sent_on": frappe.utils.now()
        })
        
        if status == "Sent":
            frappe.db.commit()

    def _send_sms_notification(self, doc_dict: Dict) -> Dict:
        """Handle SMS notification sending"""
        recipients = self._get_sms_recipients(doc_dict)
        if not recipients:
            return {"success": False, "message": "No valid recipients found"}

        message = f"{doc_dict.get('subject')}: {doc_dict.get('message')}" if doc_dict.get("subject") else doc_dict.get("message")
        valid_recipients = [self._format_phone_number(p) for p in recipients if self._validate_phone_number(p)]
        
        if not valid_recipients:
            return {"success": False, "message": "No valid phone numbers found"}

        if doc_dict.get("recipient_type") in ["Single User", "Single Patient"]:
            result = self.sms.send_sms(
                mobile=valid_recipients[0],
                message=message,
                refid=doc_dict.get("name")
            )
            return {
                "success": True,
                "recipients": 1,
                "result": result
            }
        else:
            messages = [{
                "mobile": mobile,
                "message": message,
                "refid": f"{doc_dict.get('name')}-{idx}"
            } for idx, mobile in enumerate(valid_recipients)]
            
            return self._send_bulk_sms(messages)

    def _send_bulk_sms(self, messages: List[Dict]) -> Dict:
        """Handle bulk SMS sending with proper result formatting"""
        try:
            results = self.sms.send_bulk_sms_individual(messages)
            success_count = sum(1 for r in results if r.get("status") == "success")
            
            return {
                "success": success_count > 0,
                "recipients": len(messages),
                "success_count": success_count,
                "failure_count": len(messages) - success_count,
                "results": results
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "recipients": len(messages),
                "success_count": 0,
                "failure_count": len(messages)
            }

    def _validate_phone_number(self, phone: str) -> bool:
        """Validate Somali phone number format"""
        if not phone:
            return False
        return bool(re.match(self.SOMALI_PHONE_REGEX, phone))

    def _format_phone_number(self, phone: str) -> str:
        """Format phone number to +252 format"""
        if phone.startswith("0"):
            return f"+252{phone[1:]}"
        elif phone.startswith("252"):
            return f"+{phone}"
        return phone

    def _send_push_notification(self, doc_dict: Dict) -> Dict:
        """Handle push notification sending"""
        tokens = self._get_push_tokens(doc_dict)
        if not tokens:
            return {"success": False, "message": "No device tokens found"}

        result = self.fcm.send(
            tokens=tokens,
            message=doc_dict.get("message"),
            title=doc_dict.get("title"),
            data={
                "click_action": doc_dict.get("click_action"),
                "reference_doctype": doc_dict.get("reference_doctype"),
                "reference_name": doc_dict.get("reference_name")
            },
            image=doc_dict.get("image_url") or doc_dict.get("image_file")
        )
        
        return {
            "success": result.get("success", False),
            "recipients": len(tokens),
            "success_count": result.get("success", 0),
            "failure_count": result.get("failure", 0),
            "results": result.get("responses", [])
        }

    def _get_sms_recipients(self, doc_dict: Dict) -> List[str]:
        """Get SMS recipients based on recipient_type"""
        recipient_type = doc_dict.get("recipient_type")
        
        if recipient_type == "Single User":
            if not doc_dict.get("user"):
                frappe.throw("User is required for Single User notifications")
            return [self._get_user_phone(doc_dict.get("user"))]
        
        elif recipient_type == "Single Patient":
            if not doc_dict.get("patient"):
                frappe.throw("Patient is required for Single Patient notifications")
            return [self._get_patient_phone(doc_dict.get("patient"))]
        
        elif recipient_type == "Multiple Users":
            users = [row.get("user") for row in doc_dict.get("selected_users", [])]
            return [self._get_user_phone(u) for u in users if u]
        
        elif recipient_type == "Multiple Patients":
            patients = [row.get("patient") for row in doc_dict.get("selected_patients", [])]
            return [self._get_patient_phone(p) for p in patients if p]
        
        elif recipient_type == "All Users":
            users = frappe.get_all("User", filters={"enabled": 1}, pluck="name")
            return [self._get_user_phone(u) for u in users]
        
        elif recipient_type == "All Patients":
            patients = frappe.get_all("Patient", filters={}, pluck="name")
            return [self._get_patient_phone(p) for p in patients]
            
        return []

    def _get_patient_phone(self, patient_id: str) -> Optional[str]:
        """Get phone number from patient record"""
        if not patient_id:
            return None
        return frappe.db.get_value("Patient", patient_id, "mobile")

    def _get_push_tokens(self, doc_dict: Dict) -> List[str]:
        """Get FCM tokens based on recipient_type
        
        Args:
            doc_dict: Dictionary containing notification details with:
                - recipient_type: Type of recipient
                - user: For single user (Link field)
                - patient: For single patient (Link field)
                - selected_users: For multiple users (table field)
                - selected_patients: For multiple patients (table field)
        
        Returns:
            List of FCM tokens for the specified recipients
        """
        recipient_type = doc_dict.get("recipient_type")
        
        if recipient_type == "Single User":
            if not doc_dict.get("user"):
                frappe.throw("User is required for Single User notifications")
            return self._get_user_tokens([doc_dict.get("user")])
        
        elif recipient_type == "Single Patient":
            if not doc_dict.get("patient"):
                frappe.throw("Patient is required for Single Patient notifications")
            return self._get_patient_tokens([doc_dict.get("patient")])
        
        elif recipient_type == "Multiple Users":
            users = [row.get("user") for row in doc_dict.get("selected_users", [])]
            return self._get_user_tokens(users)
        
        elif recipient_type == "Multiple Patients":
            patients = [row.get("patient") for row in doc_dict.get("selected_patients", [])]
            return self._get_patient_tokens(patients)
        
        elif recipient_type == "All Users":
            users = frappe.get_all("User", filters={"enabled": 1}, pluck="name")
            return self._get_user_tokens(users)
        
        elif recipient_type == "All Patients":
            patients = frappe.get_all("Patient", filters={}, pluck="name")
            return self._get_patient_tokens(patients)
            
        return []

    def _get_user_tokens(self, users: List[str]) -> List[str]:
        """Get FCM tokens for users"""
        if not users:
            return []
            
        if self.app_target == "Medical App":
            patients = frappe.get_all("Patient",
                filters={"user": ["in", users]},
                fields=["name", "fcm_token"])
            return [p.fcm_token for p in patients if p.fcm_token]
        else:
            users = frappe.get_all("User",
                filters={"name": ["in", users]},
                fields=["name", "fcm_token"])
            return [u.fcm_token for u in users if u.fcm_token]

    def _get_patient_tokens(self, patients: List[str]) -> List[str]:
        """Get FCM tokens for patients"""
        if not patients:
            return []
            
        patients = frappe.get_all("Patient",
            filters={"name": ["in", patients]},
            fields=["name", "fcm_token"])
        return [p.fcm_token for p in patients if p.fcm_token]
    
    
    def _get_patient_phone(self, patient_id: str) -> Optional[str]:
        """Get phone number with fallback logic"""
        if not patient_id:
            return None
            
        phone = frappe.db.get_value("Patient", patient_id, 
                                ["mobile", "phone", "user"], as_dict=True)
        
        # Try mobile first, then phone, then user's mobile
        return (phone.mobile or 
            phone.phone or 
            frappe.db.get_value("User", phone.user, "mobile"))

    def send_async(self, doc_dict: Dict):
        """Queue notification for background sending"""
        enqueue(
            method=self.send_notification,
            queue="short",
            timeout=300,  # 5 minutes
            doc_dict=doc_dict,
            job_name=f"{doc_dict.get('type')} Notification - {doc_dict.get('name')}"
        )

    # Topic Management Methods
    def subscribe_to_topic(self, users: List[str], topic_name: str) -> Dict:
        """Subscribe users to topic"""
        tokens = self._get_user_tokens(users)
        return self.fcm.subscribe_to_topic(tokens, topic_name)

    def unsubscribe_from_topic(self, users: List[str], topic_name: str) -> Dict:
        """Unsubscribe users from topic"""
        tokens = self._get_user_tokens(users)
        return self.fcm.unsubscribe_from_topic(tokens, topic_name)

    def send_to_topic(self, topic_name: str, message: str, **kwargs) -> Dict:
        """Send message to topic"""
        return self.fcm.send_to_topic(
            topic_name=topic_name,
            message=message,
            title=kwargs.get("title"),
            data=kwargs.get("data"),
            image=kwargs.get("image")
        )
        
        
        

@frappe.whitelist()
def retry_notification(name: str) -> Dict:
    """
    Retry sending a failed notification
    Args:
        name: Name of the App Notification Log document
    Returns:
        Dict with retry results
    """
    doc = frappe.get_doc("App Notification Log", name)

    if doc.status != "Failed":
        return {"success": False, "message": "Can only retry failed notifications"}

    # Convert doc to dictionary including child tables
    doc_dict = doc.as_dict()
    doc_dict["selected_users"] = [row.as_dict() for row in doc.get("selected_users", [])]
    doc_dict["selected_patients"] = [row.as_dict() for row in doc.get("selected_patients", [])]

    service = NotificationService(doc_dict.get("app_target"))
    result = service.send_notification(doc_dict)

    return {
        "success": result.get("success", False),
        "message": "Retry attempted",
        "details": result
    }
        