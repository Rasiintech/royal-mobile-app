import frappe
import requests
import json
from frappe.utils import now_datetime, now
from datetime import datetime
import uuid


class PaymentService:
    def __init__(self):
        self.api_url = "https://api.waafipay.net/asm"
        self.api_key = "API-1221796037AHX"
        self.api_user_id = "1007359"
        self.merchant_uid = "M0913615"

    def initiate_payment(self, mobile, amount, reference_id, invoice_id, description):
        """
        Initiate a direct purchase payment
        """
        request_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        # Remove +252 and ensure it's just local number like '613656021'
        cleaned_mobile = mobile.replace('+252', '').replace('252', '').lstrip('0')

        payload = {
            "schemaVersion": "1.0",
            "requestId": request_id,
            "timestamp": timestamp,
            "channelName": "WEB",
            "serviceName": "API_PURCHASE",
            "serviceParams": {
                "merchantUid": self.merchant_uid,
                "apiUserId": self.api_user_id,
                "apiKey": self.api_key,
                "paymentMethod": "MWALLET_ACCOUNT",
                "payerInfo": {
                    "accountNo": cleaned_mobile,
                },
                "transactionInfo": {
                    "referenceId": reference_id,
                    "invoiceId": invoice_id,
                    "amount": str(amount),
                    "currency": "USD",
                    "description": description
                }
            }
        }

        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            print("Status Code:", response.status_code)
            print("Raw Response:", response.text)

            data = response.json()

            if data.get("responseCode") != "2001":
                frappe.throw(data.get("responseMsg", "Payment gateway returned an error"))

            return {
                "status": "success",
                "transaction_id": data["params"]["transactionId"],
                "reference_id": data["params"]["referenceId"],
                "amount": data["params"]["txAmount"],
                "account_no": data["params"].get("accountNo"),
                "state": data["params"].get("state"),
                "issuer_transaction_id": data["params"].get("issuerTransactionId")
            }

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Waafi Purchase Error")
            frappe.throw(f"Payment failed: {str(e)}")

    def reverse_payment(self, transaction_id, description="Reversal"):
        """
        Reverse a completed payment (within 24 hours, before settlement)
        """
        request_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        payload = {
            "schemaVersion": "1.0",
            "requestId": request_id,
            "timestamp": timestamp,
            "channelName": "WEB",
            "serviceName": "API_REVERSAL",
            "serviceParams": {
                "merchantUid": self.merchant_uid,
                "apiUserId": self.api_user_id,
                "apiKey": self.api_key,
                "transactionId": transaction_id,
                "description": description
            }
        }

        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            data = response.json()

            if data.get("responseCode") != "2001":
                frappe.throw(f"Reversal failed: {data.get('responseMsg')}")

            return {
                "status": "success",
                "transaction_id": data["params"].get("transactionId"),
                "reference_id": data["params"].get("referenceId"),
                "state": data["params"].get("state"),
                "description": data["params"].get("description"),
                "message": data.get("responseMsg")
            }

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Waafi Reversal Error")
            frappe.throw(f"Reversal failed: {str(e)}")