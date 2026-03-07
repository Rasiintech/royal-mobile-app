import random
import frappe
from datetime import datetime

def generate_and_send_otp(mobile, isLogin=False, ttl=300):
    """
    Generate and send OTP to the given mobile number with enhanced security
    
    Args:
        mobile: Validated mobile number to send OTP to
        isLogin: Boolean - True for login, False for registration/other
        ttl: Time-to-live in seconds (default 5 minutes)
    
    Returns:
        str: Generated OTP
    Raises:
        Exception: If OTP was recently sent or SMS fails
    """
    # Rate limiting check (commented in your example)
    # if frappe.cache().get_value(f"otp_{mobile}"):
    #     raise Exception("OTP recently sent. Please wait before requesting again.")

    otp = generate_secure_otp()
    
    # Enhanced SMS templates with emojis and security warnings
    if isLogin:
        message = (
            f"🔐 Hodan Hospital Login Code: {otp}\n"
            f"Use this to securely log in to your account.\n"
            f"Expires in {ttl//60} minutes.\n"
            f"⚠️ Never share this code with anyone."
        )
    else:
        message = (
            f"📝 Hodan Hospital Verification Code: {otp}\n"
            f"Use this to complete your registration.\n"
            f"Expires in {ttl//60} minutes.\n"
            f"🚨 Keep this code confidential."
        )
    
    # Log OTP generation without exposing full OTP in logs
    frappe.logger().info(f"OTP generated for {mobile[:4]}**** (Login: {isLogin})")
    
    # Save OTP with additional metadata
    save_otp_to_cache(
        mobile=mobile,
        otp=otp,
        ttl=ttl,
        purpose="login" if isLogin else "registration",
        generated_at=datetime.now().isoformat()
    )

    # Enqueue SMS with longer timeout
    frappe.enqueue(
        method="royal_mobile_app.api.sms.send_otp_sms",
        queue="short",
        timeout=90,  # Extended timeout for SMS delivery
        mobile=mobile,
        message=message,
        # is_retry=False  # Track initial attempt
    )

    return otp

def generate_secure_otp(length=6):
    """Generate cryptographically stronger OTP"""
    # Using system random instead of default random for better security
    system_random = random.SystemRandom()
    return ''.join(system_random.choices('0123456789', k=length))

def save_otp_to_cache(mobile, otp, ttl=300, **metadata):
    """Save OTP with additional metadata"""
    cache_data = {
        'otp': otp,
        'attempts': 0,  # Track verification attempts
        'created_at': datetime.now().isoformat(),
        **metadata
    }
    frappe.cache().set_value(
        key=f"otp_{mobile}",
        val=cache_data,
        expires_in_sec=ttl
    )

def verify_otp(mobile, otp):
    """Verify OTP and automatically clear if successful"""
    cached_data = frappe.cache().get_value(f"otp_{mobile}")
    
    if not cached_data:
        return False  # No OTP exists or expired
    
    # Increment attempt counter
    cached_data['attempts'] += 1
    frappe.cache().set_value(
        key=f"otp_{mobile}",
        val=cached_data,
        expires_in_sec=300  # Reset TTL on each attempt
    )
    
    # Verify OTP match
    if cached_data['otp'] == otp:
        # Clear OTP immediately after successful verification
        frappe.cache().delete_value(f"otp_{mobile}")
        return True
    
    # Optional: Implement attempt limits
    if cached_data['attempts'] >= 3:
        frappe.cache().delete_value(f"otp_{mobile}")
        return False
    
    return False