# apps/royal_mobile_app/royal_mobile_app/utils/erpnext_utils.py

import frappe
from frappe.utils import cint, flt


def get_mobile_app_defaults():
    """Fetches defaults from Mobile App Settings (company, payment, appointment caps)."""

    settings = frappe.get_single("Mobile App Settings")

    return {
        "company": settings.default_company,
        "cost_center": settings.default_cost_center,
        "mode_of_payment": settings.default_mode_of_payment,
        "appointments_per_doctor_limit": cint(
            getattr(settings, "appointments_per_doctor_limit", None) or 50
        ),
        "appointment_end_time": settings.appointment_end_time,
        "enable_future_appointments": cint(getattr(settings, "enable_future_appointments", None) or 0),
        "source_order": settings.source_order,
        "enable_mobile_consultation_fee": cint(
            getattr(settings, "enable_mobile_consultation_fee", None) or 0
        ),
        "mobile_consultation_item": getattr(settings, "mobile_consultation_item", None),
        "mobile_consultation_rate": flt(getattr(settings, "mobile_consultation_rate", None) or 0),
        "payment_gateway_fee_percentage": flt(
            getattr(settings, "payment_gateway_fee_percentage", None) or 0
        ),
    }


def apply_payment_gateway_fee(amount, percentage=None, defaults=None):
    """
    Reusable Waafi / payment-gateway pass-through fee.

    final = amount * (1 + payment_gateway_fee_percentage / 100)
    Example: 9 * (1 + 1/100) = 9.09
    """
    base = flt(amount or 0)
    if percentage is None:
        defaults = defaults or get_mobile_app_defaults()
        percentage = flt(defaults.get("payment_gateway_fee_percentage") or 0)

    percentage = flt(percentage or 0)
    if percentage <= 0:
        return flt(base, 2)

    return flt(base * (1 + (percentage / 100.0)), 2)


def get_mobile_consultation_charge(op_consulting_charge, defaults=None):
    """
    Doctor mobile charge shown in app:
    (op_consulting_charge + mobile_consultation_rate), then apply payment_gateway_fee_percentage.

    If mobile consultation fee is disabled, return original charge only.
    """
    defaults = defaults or get_mobile_app_defaults()
    base_charge = flt(op_consulting_charge or 0)

    if not defaults.get("enable_mobile_consultation_fee"):
        return base_charge

    mobile_rate = flt(defaults.get("mobile_consultation_rate") or 0)
    subtotal = base_charge + mobile_rate
    return apply_payment_gateway_fee(subtotal, defaults=defaults)
