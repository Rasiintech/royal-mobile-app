# frappe-bench/apps/royal_mobile_app/royal_mobile_app/services/hormuud_sms_service.py

from typing import Dict, List, Optional
from frappe.utils.background_jobs import enqueue
import base64
import requests
import frappe
from datetime import datetime
import time


class HormuudSMSService:
	def __init__(self):
		self.settings = frappe.get_single("Mobile Integrations Settings")
		base_url = (
			(self.settings.hormuud_api_url or "").strip() or "https://smsapi.hormuud.com"
		).rstrip("/")
		self.BASE_URL = base_url
		self.SMS_ENDPOINT = f"{base_url}/api/sms/Send"
		self.BULK_SMS_ENDPOINT = f"{base_url}/api/Outbound/SendBulkSMS"

		self.username = (self.settings.hormuud_username or "").strip()
		try:
			self.password = self.settings.get_password("hormuud_password") or ""
		except Exception:
			self.password = ""
		self.sender_id = (self.settings.hormuud_sender_id or "").strip()
		self.sms_character_limit = self.settings.sms_character_limit or 150

		if not self.username or not self.password:
			frappe.throw(
				"Hormuud SMS credentials are not configured. "
				"Set them in Mobile Integrations Settings."
			)

	def _post_with_retry(
		self,
		url: str,
		headers: Dict,
		data: Dict,
		retries: int = 2,
		timeout: int = 10,
	) -> Optional[requests.Response]:
		"""
		Retry on clear transport failures only.
		Does not retry when Hormuud returns HTTP 200 with an invalid body
		(avoids duplicate SMS sends).
		"""
		last_exception = None
		last_response = None

		for attempt in range(retries + 1):
			try:
				response = requests.post(url, headers=headers, json=data, timeout=timeout)

				if response.status_code == 200:
					response_data = response.json()
					if self._is_valid_response(response_data):
						frappe.logger().debug(f"SMS API success on attempt {attempt+1}")
						return response
					frappe.logger().warning(f"Invalid API response: {response_data}")
					last_response = response
				else:
					response.raise_for_status()

			except requests.exceptions.RequestException as e:
				last_exception = e
				frappe.logger().warning(f"Attempt {attempt+1} failed: {str(e)}")

			# Don't retry if we got a 200 but invalid content
			if last_response and last_response.status_code == 200:
				break

			if attempt < retries:
				time.sleep(min(2 ** attempt, 5))

		if last_response and last_response.status_code == 200:
			return last_response

		raise Exception(
			f"POST to {url} failed after {retries+1} attempts. "
			f"Last error: {str(last_exception)}"
		)

	def _is_valid_response(self, response_data: dict) -> bool:
		return (
			isinstance(response_data, dict)
			and str(response_data.get("ResponseCode")) == "200"
		)

	def _validate_message(self, message: str):
		if not message:
			frappe.throw("Message cannot be empty")
		if len(message) > self.sms_character_limit:
			frappe.throw(f"Message exceeds {self.sms_character_limit} character limit")

	def _auth_headers(self) -> Dict:
		credentials = f"{self.username}:{self.password}"
		encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
		return {
			"Authorization": f"Basic {encoded}",
			"Content-Type": "application/json",
		}

	def _success_response(
		self,
		mobile: str,
		refid: str,
		hormuud_data: Optional[dict] = None,
		message: str = "SMS sent successfully",
	) -> Dict:
		data = hormuud_data or {}
		payload = data.get("Data") if isinstance(data.get("Data"), dict) else {}
		return {
			"success": True,
			"message": message
			or data.get("ResponseMessage")
			or payload.get("Description")
			or "SMS sent successfully",
			"mobile": mobile,
			"refid": refid,
			"message_id": payload.get("MessageID"),
		}

	def _error_response(
		self,
		mobile: str,
		refid: str,
		message: str,
		hormuud_data: Optional[dict] = None,
	) -> Dict:
		return {
			"success": False,
			"message": message,
			"mobile": mobile,
			"refid": refid,
			"message_id": None,
		}

	def _normalize_hormuud_response(
		self, mobile: str, refid: str, hormuud_data: dict
	) -> Dict:
		if self._is_valid_response(hormuud_data):
			return self._success_response(
				mobile=mobile,
				refid=refid,
				hormuud_data=hormuud_data,
				message=hormuud_data.get("ResponseMessage") or "SMS sent successfully",
			)

		return self._error_response(
			mobile=mobile,
			refid=refid,
			message=hormuud_data.get("ResponseMessage")
			or hormuud_data.get("message")
			or "SMS sending failed",
			hormuud_data=hormuud_data,
		)

	def send_sms(self, mobile: str, message: str, refid="0", validity=0) -> Dict:
		"""
		Send a single SMS via Hormuud Basic-auth API.

		Always returns:
		{
			"success": bool,
			"message": str,
			"mobile": str,
			"refid": str,
			"message_id": str | None,
		}
		"""
		self._validate_message(message)
		refid = str(refid or "0")

		payload = {
			"senderid": self.sender_id,
			"refid": refid,
			"mobile": mobile,
			"message": message,
			"validity": validity,
		}

		try:
			response = self._post_with_retry(
				self.SMS_ENDPOINT, self._auth_headers(), payload
			)
			return self._normalize_hormuud_response(mobile, refid, response.json())
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), f"Hormuud SMS failed to {mobile}")
			return self._error_response(mobile=mobile, refid=refid, message=str(e))

	def send_bulk_sms_individual(self, messages: list) -> List[Dict]:
		"""
		Send each SMS individually. Returns a list of normalized send_sms responses.
		"""
		results = []
		for msg in messages:
			result = self.send_sms(
				mobile=msg["mobile"],
				message=msg["message"],
				refid=msg.get("refid", "bulk-ref"),
				validity=msg.get("validity", 0),
			)
			results.append(result)
		return results

	def send_bulk_sms(self, messages: list) -> List[Dict]:
		"""
		Send via Hormuud bulk API in chunks of 20.
		Each chunk returns a normalized response dict.
		"""
		if not messages:
			return []

		now = datetime.utcnow().isoformat()
		headers = self._auth_headers()
		results = []

		def chunk_list(data, chunk_size):
			for i in range(0, len(data), chunk_size):
				yield data[i : i + chunk_size]

		for chunk in chunk_list(messages, 20):
			bulk_payload = []
			for msg in chunk:
				bulk_payload.append(
					{
						"refid": msg.get("refid", "bulk-ref"),
						"mobile": msg["mobile"],
						"message": msg["message"],
						"senderid": self.sender_id,
						"mType": 0,
						"eType": 0,
						"validity": msg.get("validity", 0),
						"delivery": msg.get("delivery", 0),
						"UDH": "",
						"RequestDate": msg.get("RequestDate", now),
					}
				)

			mobiles = [m["mobile"] for m in chunk]
			try:
				response = self._post_with_retry(
					self.BULK_SMS_ENDPOINT, headers, bulk_payload
				)
				hormuud_data = response.json()
				if self._is_valid_response(hormuud_data):
					results.append(
						{
							"success": True,
							"message": hormuud_data.get("ResponseMessage")
							or "Bulk SMS sent successfully",
							"mobiles": mobiles,
							"count": len(chunk),
							"message_id": (hormuud_data.get("Data") or {}).get(
								"MessageID"
							)
							if isinstance(hormuud_data.get("Data"), dict)
							else None,
						}
					)
				else:
					results.append(
						{
							"success": False,
							"message": hormuud_data.get("ResponseMessage")
							or "Bulk SMS failed",
							"mobiles": mobiles,
							"count": len(chunk),
							"message_id": None,
						}
					)
			except Exception as e:
				frappe.logger().error(f"Bulk SMS chunk failed: {str(e)}")
				results.append(
					{
						"success": False,
						"message": str(e),
						"mobiles": mobiles,
						"count": len(chunk),
						"message_id": None,
					}
				)

		return results

	def send_async_sms(self, mobile: str, message: str, refid="0", validity=0):
		"""Queue SMS for background sending"""
		enqueue(
			method=self.send_sms,
			queue="short",
			mobile=mobile,
			message=message,
			refid=refid,
			validity=validity,
		)

	def enqueue_bulk_sms(self, messages: list):
		"""Send SMS in background using bulk logic"""
		enqueue(
			method=self.send_bulk_sms,
			queue="long",
			messages=messages,
		)
