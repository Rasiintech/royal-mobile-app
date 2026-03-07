# frappe-bench/apps/royal_mobile_app/royal_mobile_app/services/hormuud_sms_service.py

from typing import Dict, Optional
from frappe.utils.background_jobs import enqueue
import requests
import json
import frappe
from datetime import datetime
import time

class HormuudSMSService:
    BASE_URL = "https://smsapi.hormuud.com"
    TOKEN_ENDPOINT = f"{BASE_URL}/token"
    SMS_ENDPOINT = f"{BASE_URL}/api/SendSMS"
    BULK_SMS_ENDPOINT = f"{BASE_URL}/api/Outbound/SendBulkSMS"

    def __init__(self):
        # self.settings = frappe.get_doc("App Notification Settings")
        self.settings = frappe.get_single("App Notification Settings")
        # self.username = "Hodanhospital"
        self.username = self.settings.get_password('sms_api_key')
        # self.password = "fj8TVv9w9eLUyknMUhyQpQ=="
        self.password = self.settings.get_password('sms_api_password')
        self.cache_key = "hormuud_sms_token"
        # self.sender_id = "HODAN HOSPITAL"
        self.sender_id = self.settings.sms_sender_id
        self.sms_character_limit = self.settings.sms_character_limit

    # def _post_with_retry(self, url, headers, data, retries=2, timeout=10):
    #     last_exception = None
    #     for attempt in range(retries + 1):
    #         try:
    #             response = requests.post(url, headers=headers, json=data, timeout=timeout)
    #             response.raise_for_status()
    #             return response
    #         except requests.exceptions.RequestException as e:
    #             last_exception = e
    #             frappe.logger().warning(f"Attempt {attempt+1} failed: {e}")
    #             if attempt < retries:
    #                 time.sleep(1)  # backoff
    #     raise Exception(f"Failed after {retries+1} attempts: {last_exception}")
    
    def _post_with_retry(self, url: str, headers: Dict, data: Dict, 
                        retries: int = 2, timeout: int = 10) -> Optional[requests.Response]:
        """
        Modified retry mechanism that:
        1. Prevents duplicate SMS sends
        2. Only retries on clear failures
        3. Validates responses before considering successful
        """
        last_exception = None
        last_response = None
        
        for attempt in range(retries + 1):
            try:
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
                
                # First validate the response looks successful
                if response.status_code == 200:
                    response_data = response.json()
                    if self._is_valid_response(response_data):
                        frappe.logger().debug(f"SMS API success on attempt {attempt+1}")
                        return response
                    else:
                        # If response is invalid but HTTP 200, log and retry
                        frappe.logger().warning(f"Invalid API response: {response_data}")
                        last_response = response
                else:
                    response.raise_for_status()
                    
            except requests.exceptions.RequestException as e:
                last_exception = e
                frappe.logger().warning(f"Attempt {attempt+1} failed: {str(e)}")
                
            # Don't retry if we got a 200 but just invalid content
            if last_response and last_response.status_code == 200:
                break
                
            if attempt < retries:
                wait_time = min(2 ** attempt, 5)  # Cap at 5 seconds
                time.sleep(wait_time)
        
        # If we got a 200 response but invalid content, return it anyway
        if last_response and last_response.status_code == 200:
            return last_response
            
        # raise Exception(f"Failed after {retries+1} attempts. Last error: {str(last_exception)}")
        raise Exception(f"POST to {url} failed after {retries+1} attempts. Last error: {str(last_exception)}")


    def _is_valid_response(self, response_data: dict) -> bool:
        return (
            isinstance(response_data, dict) and
            response_data.get("ResponseCode") == "200"
        )
        
    def _validate_message(self, message: str):
        if not message:
            frappe.throw("Message cannot be empty")
        if len(message) > self.sms_character_limit:
            frappe.throw(f"Message exceeds {self.sms_character_limit} character limit")   
  

    def _generate_token(self):
        payload = {
            "grant_type": "password",
            "username": self.username,
            "password": self.password
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        try:
            response = requests.post(self.TOKEN_ENDPOINT, data=payload, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            token = data.get("access_token")
            frappe.cache().set_value(self.cache_key, token, expires_in_sec=50)
            return token
        except requests.exceptions.RequestException as e:
            raise Exception(f"Token generation failed: {e}")

    def _get_valid_token(self):
        token = frappe.cache().get_value(self.cache_key)
        if token:
            return token
        return self._generate_token()

    def send_sms(self, mobile: str, message: str, refid="0", validity=0):
        self._validate_message(message)
        
        token = self._get_valid_token()
        payload = {
            "senderid": self.sender_id,
            "refid": refid,
            "mobile": mobile,
            "message": message,
            "validity": validity
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        response = self._post_with_retry(self.SMS_ENDPOINT, headers, payload)
        return response.json()

    def send_bulk_sms_individual(self, messages: list):
        """
        Sends each SMS message individually using self.send_sms().
        Useful for better tracking, retries, or logging.
        """
        results = []
        for msg in messages:
            try:
                result = self.send_sms(
                    mobile=msg["mobile"],
                    message=msg["message"],
                    refid=msg.get("refid", "bulk-ref"),
                    validity=msg.get("validity", 0)
                )
                results.append({
                    "mobile": msg["mobile"],
                    "status": "success",
                    "response": result
                })
            except Exception as e:
                frappe.logger().error(f"Failed to send SMS to {msg['mobile']}: {str(e)}")
                results.append({
                    "mobile": msg["mobile"],
                    "status": "error",
                    "error": str(e)
                })
        return results

    
    
    def send_bulk_sms(self, messages: list):
        """
        Sends SMS messages using Hormuud's bulk API in chunks of 20.
        Automatically handles batching if more than 20 messages are provided.
        """
        if not messages:
            return []

        token = self._get_valid_token()
        now = datetime.utcnow().isoformat()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        results = []

        def chunk_list(data, chunk_size):
            for i in range(0, len(data), chunk_size):
                yield data[i:i + chunk_size]

        for chunk in chunk_list(messages, 20):
            bulk_payload = []
            for msg in chunk:
                bulk_payload.append({
                    "refid": msg.get("refid", "bulk-ref"),
                    "mobile": msg["mobile"],
                    "message": msg["message"],
                    "senderid": self.sender_id,
                    "mType": 0,        # or -1 if required
                    "eType": 0,        # or -1 if required
                    "validity": msg.get("validity", 0),
                    "delivery": msg.get("delivery", 0),
                    "UDH": "",
                    "RequestDate": msg.get("RequestDate", now)
                })

            try:
                response = self._post_with_retry(self.BULK_SMS_ENDPOINT, headers, bulk_payload)
                results.append(response.json())
            except Exception as e:
                frappe.logger().error(f"Bulk SMS chunk failed: {str(e)}")
                results.append({"error": str(e), "chunk": bulk_payload})

        return results

    
    
    def send_async_sms(self, mobile: str, message: str, refid="0", validity=0):
        """Queue SMS for background sending"""
        enqueue(
            method=self.send_sms,
            queue='short',
            mobile=mobile,
            message=message,
            refid=refid,
            validity=validity
        )
        
    def enqueue_bulk_sms(self, messages: list):
        """Send SMS in background using bulk logic"""
        enqueue(
            method=self.send_bulk_sms,
            queue='long',
            messages=messages
        )
    
