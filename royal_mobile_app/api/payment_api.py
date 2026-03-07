import frappe
from frappe import _
from royal_mobile_app.services.payment_services import PaymentService

@frappe.whitelist(allow_guest=True)
def initiate_payment(mobile, amount, reference_id, invoice_id, description):
    """Endpoint to initiate direct purchase payment"""
    try:
        if not all([mobile, amount, reference_id, invoice_id]):
            frappe.throw(_("Missing required parameters: mobile, amount, reference_id, invoice_id"))
        
        try:
            amount = float(amount)
        except ValueError:
            frappe.throw(_("Amount must be a valid number"))
        
        payment_service = PaymentService()
        result = payment_service.initiate_payment(
            mobile=mobile,
            amount=amount,
            reference_id=reference_id,
            invoice_id=invoice_id,
            description=description
        )
        
        return {
            "success": True,
            "data": result,
            "message": "Payment initiated successfully"
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Payment Initiation API Error")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to initiate payment"
        }

@frappe.whitelist(allow_guest=True)
def reverse_payment(transaction_id, description="Reversal"):
    """Endpoint to reverse a payment"""
    try:
        if not transaction_id:
            frappe.throw(_("Missing required parameter: transaction_id"))
        
        payment_service = PaymentService()
        result = payment_service.reverse_payment(
            transaction_id=transaction_id,
            description=description
        )
        
        return {
            "success": True,
            "data": result,
            "message": "Payment reversed successfully"
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Payment Reversal API Error")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to reverse payment"
        }