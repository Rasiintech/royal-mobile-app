import frappe
from royal_mobile_app.services.hormuud_sms_service import HormuudSMSService


def send_appointment_sms(mobile, message):
	try:
		sms = HormuudSMSService()
		result = sms.send_sms(mobile=mobile, message=message)
		if not result.get("success"):
			frappe.log_error(
				result.get("message") or "Unknown SMS error",
				f"SMS sending failed to {mobile}",
			)
		return result
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"SMS sending failed to {mobile}")
		return {
			"success": False,
			"message": "SMS sending failed",
			"mobile": mobile,
			"refid": "0",
			"message_id": None,
		}


@frappe.whitelist(allow_guest=True)
def send_otp_sms(mobile, message, **kwargs):
	try:
		sms = HormuudSMSService()
		result = sms.send_sms(mobile=mobile, message=message)
		if not result.get("success"):
			frappe.log_error(
				result.get("message") or "Unknown SMS error",
				f"OTP SMS sending failed to {mobile}",
			)
		return result
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"OTP SMS sending failed to {mobile}")
		return {
			"success": False,
			"message": "OTP SMS sending failed",
			"mobile": mobile,
			"refid": "0",
			"message_id": None,
		}
