# apps/royal_mobile_app/royal_mobile_app/utils/erpnext_utils.py

import frappe
from frappe.utils import cint


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
    }
