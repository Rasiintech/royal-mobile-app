import frappe
from royal_mobile_app.services.hormuud_sms_service import HormuudSMSService

def send_appointment_sms(mobile, message):
    try:
        sms = HormuudSMSService()
        sms.send_sms(mobile=mobile, message=message)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"SMS sending failed to {mobile}")

@frappe.whitelist(allow_guest=True)
def send_otp_sms(mobile, message,**kwargs):
    try:
        sms = HormuudSMSService()
        sms.send_sms(mobile=mobile, message=message)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"OTP SMS sending failed to {mobile}")    