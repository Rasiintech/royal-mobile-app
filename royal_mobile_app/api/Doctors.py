import frappe
from royal_mobile_app.utils.guest_api_utils import run_as_administrator_if_guest
from royal_mobile_app.utils.response_utils import response_util
import time


@frappe.whitelist(allow_guest=True)
def get_all_doctors():
    try:
        with run_as_administrator_if_guest():
            doctors = frappe.get_all(
                "Healthcare Practitioner",
                filters={"status": "Active", "hide_doctor": 0},
                fields=[
                    "name",
                    "op_consulting_charge",
                    "department",
                    "image",
                    "about",
                    "experience_years",
                    "available_time",
                    "hide_doctor",
                    "total_patients",
                    "rating"
                ]
            )

            departments = frappe.get_all(
                "Medical Department",
                fields=["name", "department", "image"]
            )

            if not doctors:
                return response_util(
                    status="error",
                    message="No doctors found in the system.",
                    data=None,
                    http_status_code=404
                )

            return response_util(
                status="success",
                message="Doctors fetched successfully",
                data={"doctors": doctors, "departments": departments},
                http_status_code=200
            )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get All Doctors Error")
        return response_util(
            status="error",
            message="An error occurred while fetching doctors.",
            error=e,
            data=None,
            http_status_code=500
        )
    
@frappe.whitelist(allow_guest=True)
def get_doctors_by_department(department):
    try:
        with run_as_administrator_if_guest():
            doctors = frappe.get_all(
                "Healthcare Practitioner",
                filters={
                    "status": "Active",
                    "hide_doctor": 0,
                    "department": department
                },
                fields=["practitioner_name", "op_consulting_charge", "department", "image", "about", "experience_years", "available_time", "hide_doctor", "total_patients", "rating"]
            )

            if not doctors:
                frappe.response['http_status_code'] = 404
                return {
                    "status": "error",
                    "msg": "No doctors found in the system.",
                    "Data": None
                }

            frappe.response['http_status_code'] = 200
            return {
                "status": "success",
                "msg": "Doctors found successfully.",
                "Data": doctors
            }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Doctors by Department Error")
        frappe.response['http_status_code'] = 500
        return {
            "status": "error",
            "msg": "An error occurred while fetching doctors by department.",
            "error": str(e),
            "Data": None
        }


@frappe.whitelist(allow_guest=True)
def get_all_departments():
    try:
        with run_as_administrator_if_guest():
            departments = frappe.get_all(
                "Medical Department",
                fields=["name", "department", "image"]
            )

            if not departments:
                frappe.response['http_status_code'] = 404
                return {
                    "status": "error",
                    "msg": "No departments found in the system.",
                    "Data": None
                }

            frappe.response['http_status_code'] = 200
            return {
                "status": "success",
                "msg": "Departments found successfully.",
                "Data": departments
            }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get All Departments Error")
        frappe.response['http_status_code'] = 500
        return {
            "status": "error",
            "msg": "An error occurred while fetching departments.",
            "Data": None,
            "error": str(e)
        }
