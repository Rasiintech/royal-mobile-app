import frappe
import time
from frappe.utils import now_datetime
from royal_mobile_app.utils.response_utils import response_util

@frappe.whitelist()
def get_all_banners():
    start_time = time.time()

    try:
        current_time = now_datetime()

        # Step 1: Fetch all banners
        banners = frappe.get_all(
            "Doctor banners",  # or rename to just "Banners"
            fields=[
                "name",
                "banner_image",
                "banner_type",
                "title",
                "description",
                "details",
                "valid_from",
                "valid_till"
            ],
            order_by="valid_from desc"
        )

        # Step 2: Filter only expired 'Service' banners
        active_banners = []
        for banner in banners:
            if banner["banner_type"] == "Service":
                valid_till = banner.get("valid_till")
                # if not valid_till or valid_till > current_time:
                # Only include if valid_till is present and in the future
                if valid_till and valid_till > current_time:
                    active_banners.append(banner)
            else:
                active_banners.append(banner)


        if not active_banners:
            return response_util(
                status="error",
                message="No banners found.",
                data=[],
                http_status_code=404
            )

        return response_util(
            status="success",
            message="Banners fetched successfully.",
            data=active_banners,
            http_status_code=200
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_all_banners failed")
        return response_util(
            status="error",
            message="An error occurred while fetching banners.",
            data=None,
            error=str(e),
            http_status_code=500
        )
