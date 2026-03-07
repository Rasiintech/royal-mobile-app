import requests
import base64
import frappe
import json
import random
from datetime import datetime, timedelta
from royal_mobile_app.utils.response_utils import response_util
from frappe.utils.redis_wrapper import RedisWrapper
from frappe.utils import get_datetime

# Initialize Redis
redis = RedisWrapper()

class HormuudSMS:
    def __init__(self):
        hormuud_username = "Hodanhospital"
        hormuud_password = "fj8TVv9w9eLUyknMUhyQpQ=="
        
    def get_auth_token(self):
        """Get bearer token using username and password"""
        try:
            url = "https://smsapi.hormuud.com/token"
            payload = f"grant_type=password&username={self.hormuud_username}&password={self.hormuud_password}"
            headers = {'content-type': 'application/x-www-form-urlencoded'}
            
            response = requests.post(url, data=payload, headers=headers)
            response.raise_for_status()
            
            return response.json().get("access_token")
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Hormuud Token Error")
            return None
    
    def send_sms(self, mobile, message, sender_id=None):
        """Send SMS using Hormuud API"""
        try:
            token = self.get_auth_token()
            if not token:
                return False, "Failed to get authentication token"
            
            url = "https://smsapi.hormuud.com/api/SendSMS"
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                "mobile": mobile,
                "message": message,
                "senderid": sender_id or self.config.default_sender_id,
                "validity": 5  # 5 minutes validity
            }
            
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            return True, "SMS sent successfully"
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Hormuud SMS Error")
            return False, str(e)

@frappe.whitelist(allow_guest=True)
def send_otp(mobile_number):
    """Send OTP to the provided mobile number and store in Redis"""
    if not mobile_number:
        return response_util(
            status="error",
            message="Mobile number is required.",
            http_status_code=400
        )

    try:
        # Generate a 6-digit OTP
        otp = str(random.randint(100000, 999999))
        otp_message = f"Your OTP is {otp}. Valid for 5 minutes."
        
        # Generate a verification token (valid for 50 seconds)
        verification_token = frappe.generate_hash(length=32)
        
        # Store in Redis with expiry
        # OTP data structure: { "otp": "123456", "attempts": 0 }
        otp_data = {
            "otp": otp,
            "attempts": 0,  # Track failed attempts
            "token": verification_token  # Generated token
        }
        
        # Store with 5 minute expiry (300 seconds)
        redis.setex(f"otp:{mobile_number}", 300, json.dumps(otp_data))
        
        # Send SMS
        sms = HormuudSMS()
        success, message = sms.send_sms(mobile_number, otp_message)
        
        if not success:
            return response_util(
                status="error",
                message=f"Failed to send OTP: {message}",
                http_status_code=500
            )
        
        return response_util(
            status="success",
            message="OTP sent successfully",
            data={
                "verification_token": verification_token,
                "expires_in": 50  # Token validity in seconds
            },
            http_status_code=200
        )
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Send OTP Error")
        return response_util(
            status="error",
            message="An error occurred while sending OTP",
            error=e,
            http_status_code=500
        )

@frappe.whitelist(allow_guest=True)
def verify_otp(mobile_number, otp, verification_token):
    """Verify the provided OTP using Redis storage"""
    if not all([mobile_number, otp, verification_token]):
        return response_util(
            status="error",
            message="Mobile number, OTP and verification token are required.",
            http_status_code=400
        )

    try:
        # Get OTP data from Redis
        otp_data = redis.get(f"otp:{mobile_number}")
        if not otp_data:
            return response_util(
                status="error",
                message="OTP expired or not found",
                http_status_code=400
            )
        
        otp_data = json.loads(otp_data)
        
        # Verify the verification token first
        if otp_data.get("token") != verification_token:
            return response_util(
                status="error",
                message="Invalid verification token",
                http_status_code=400
            )
        
        # Check attempts (allow max 3 attempts)
        if otp_data.get("attempts", 0) >= 3:
            # Delete the OTP after too many attempts
            redis.delete(f"otp:{mobile_number}")
            return response_util(
                status="error",
                message="Too many attempts. OTP invalidated.",
                http_status_code=400
            )
        
        # Verify OTP
        if otp_data.get("otp") != otp:
            # Increment attempt counter
            otp_data["attempts"] += 1
            redis.setex(f"otp:{mobile_number}", 
                       redis.ttl(f"otp:{mobile_number}"),  # Maintain existing TTL
                       json.dumps(otp_data))
            
            return response_util(
                status="error",
                message="Invalid OTP",
                http_status_code=400
            )
        
        # OTP is valid - generate short-lived auth token (50 seconds)
        auth_token = frappe.generate_hash(length=32)
        auth_token_expiry = get_datetime() + timedelta(seconds=50)
        
        # Store auth token in Redis
        redis.setex(f"auth_token:{auth_token}", 50, json.dumps({
            "mobile": mobile_number,
            "verified_at": str(get_datetime())
        }))
        
        # Delete the OTP data as it's been used
        redis.delete(f"otp:{mobile_number}")
        
        return response_util(
            status="success",
            message="OTP verified successfully",
            data={
                "auth_token": auth_token,
                "expires_in": 50
            },
            http_status_code=200
        )
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Verify OTP Error")
        return response_util(
            status="error",
            message="An error occurred while verifying OTP",
            error=e,
            http_status_code=500
        )

@frappe.whitelist(allow_guest=True)
def validate_auth_token(auth_token):
    """Validate the short-lived auth token"""
    if not auth_token:
        return response_util(
            status="error",
            message="Auth token is required",
            http_status_code=400
        )
    
    try:
        token_data = redis.get(f"auth_token:{auth_token}")
        if not token_data:
            return response_util(
                status="error",
                message="Invalid or expired token",
                http_status_code=400
            )
        
        token_data = json.loads(token_data)
        
        return response_util(
            status="success",
            message="Token is valid",
            data={
                "mobile": token_data.get("mobile"),
                "verified_at": token_data.get("verified_at")
            },
            http_status_code=200
        )
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Validate Auth Token Error")
        return response_util(
            status="error",
            message="An error occurred while validating token",
            error=e,
            http_status_code=500
        )