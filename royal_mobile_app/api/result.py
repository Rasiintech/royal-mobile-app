import frappe
import re 
from royal_mobile_app.utils.response_utils import response_util

def clean_html(raw_html):
    """Remove HTML tags from a string."""
    if not raw_html or not isinstance(raw_html, str):
        return raw_html
    return re.sub(r'<[^>]*>', '', raw_html)

@frappe.whitelist(allow_guest=True)
def get_lab_results_by_mobile(mobile=None):
    try:
        if not mobile:
            return response_util(
                status="error",
                message="Mobile number is required.",
                http_status_code=400
            )

        # Step 1: Get patients
        patient_records = frappe.get_all(
            "Patient",
            filters={"mobile": mobile},
            fields=["name", "patient_name"]
        )

        if not patient_records:
            return response_util(
                status="error",
                message=f"No patients found for mobile: {mobile}",
                data=[],
                http_status_code=404
            )

        patient_name_map = {p["name"]: p["patient_name"] for p in patient_records}
        patient_ids = list(patient_name_map.keys())

        # Only return last 90 days
        cutoff_date = frappe.utils.add_days(frappe.utils.today(), -90)

        # Step 2: Fetch Lab Results
        lab_results = frappe.get_all(
            "Lab Result",
            filters={"patient": ["in", patient_ids], "docstatus": 1, "creation": [">=", cutoff_date]},
            fields=["name", "patient", "patient_name", "practitioner", "type", "template", "docstatus"],
            order_by="modified desc"
        )

        # Step 3: Attach test items (with HTML sanitization)
        for result in lab_results:
            items = frappe.get_all(
                "Normal Test Result",
                filters={"parent": result["name"]},
                fields=[
                    "test",
                    "lab_test_event",
                    "result_value",
                    "normal_range",
                    "lab_test_uom",
                    "lab_test_comment",
                    "flag"
                ]
            )
            
            # Clean HTML from each item's fields
            for item in items:
                if "normal_range" in item:
                    item["normal_range"] = clean_html(item["normal_range"])
                if "lab_test_comment" in item:
                    item["lab_test_comment"] = clean_html(item["lab_test_comment"])
            
            result["items"] = items
            result["patient_name"] = patient_name_map.get(result["patient"], "")

        return response_util(
            status="success",
            message="Lab results retrieved successfully.",
            data=lab_results,
            http_status_code=200
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Lab Results by Mobile Error")
        return response_util(
            status="error",
            message="Internal Server Error",
            error=str(e),
            http_status_code=500
        )