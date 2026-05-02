import frappe
import time
from frappe.utils import now_datetime
from royal_mobile_app.utils.guest_api_utils import run_as_administrator_if_guest
from royal_mobile_app.utils.response_utils import response_util

@frappe.whitelist(allow_guest=True)
def get_all_banners():
    start_time = time.time()

    try:
        with run_as_administrator_if_guest():
            current_time = now_datetime()

            banners = frappe.get_all(
                "Doctor banners",
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

            active_banners = []
            for banner in banners:
                if banner["banner_type"] == "Service":
                    valid_till = banner.get("valid_till")
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
