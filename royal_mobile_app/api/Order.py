import frappe
import re
from royal_mobile_app.utils.guest_api_utils import run_as_administrator_if_guest
from royal_mobile_app.utils.response_utils import response_util
from royal_mobile_app.utils.erpnext_utils import get_mobile_app_defaults
from royal_mobile_app.utils.trace_utils import log_mobile_api_failure, order_trace_context


def _order_error(api, step, sales_order_id=None, so_doc=None, mobile=None, **kwargs):
    """Log failure to Error Log and return standard error response (unchanged shape)."""
    log_mobile_api_failure(
        api=api,
        step=step,
        context=order_trace_context(sales_order_id=sales_order_id, so_doc=so_doc, mobile=mobile),
        error=kwargs.get("error"),
        http_status_code=kwargs.get("http_status_code"),
    )
    return response_util(
        status=kwargs.get("status", "error"),
        message=kwargs.get("message", ""),
        data=kwargs.get("data"),
        error=kwargs.get("error"),
        http_status_code=kwargs.get("http_status_code", 400),
    )


def _handle_credit_limit_error(api, step, sales_order_id, so_doc, message):
    approvers = []
    emails = re.findall(r'[\w\.-]+@[\w\.-]+', message)
    names = re.findall(r'<li>(.*?)\s\(', message)

    if names and emails and len(names) == len(emails):
        approvers = [{"name": n.strip(), "email": e.strip()} for n, e in zip(names, emails)]
    else:
        approvers = emails or ["Credit approvers not found in message."]

    log_mobile_api_failure(
        api=api,
        step=step,
        context=order_trace_context(sales_order_id=sales_order_id, so_doc=so_doc),
        error=message,
        http_status_code=400,
    )
    return response_util(
        status="error",
        message="Customer's credit limit has been exceeded. Approval is required before proceeding.",
        data=approvers,
        error=message,
        http_status_code=400,
    )


@frappe.whitelist(allow_guest=True)
def validate_sales_order_for_conversion(sales_order_id=None):
    api = "validate_sales_order_for_conversion"
    so_doc = None
    try:
        if not sales_order_id:
            return _order_error(
                api,
                "missing_sales_order_id",
                sales_order_id=sales_order_id,
                message="sales_order_id parameter is required.",
                http_status_code=400,
            )

        with run_as_administrator_if_guest():
            so_doc = frappe.get_doc("Sales Order", sales_order_id)

            if so_doc.docstatus != 1:
                return _order_error(
                    api,
                    "sales_order_not_submitted",
                    sales_order_id=sales_order_id,
                    so_doc=so_doc,
                    message="Only submitted Sales Orders can be converted to Sales Invoices.",
                    http_status_code=400,
                )

            if not getattr(so_doc, "ref_practitioner", None):
                return _order_error(
                    api,
                    "missing_ref_practitioner",
                    sales_order_id=sales_order_id,
                    so_doc=so_doc,
                    message="Sales Order is missing Referring Practitioner which is required in the Sales Invoice.",
                    http_status_code=400,
                )

            for item in so_doc.items:
                if not item.rate or item.rate == 0:
                    return _order_error(
                        api,
                        "zero_item_rate",
                        sales_order_id=sales_order_id,
                        so_doc=so_doc,
                        message=f"Rate cannot be zero for item: {item.item_name} (Row: {item.idx})",
                        http_status_code=400,
                    )

            get_mobile_app_defaults()

            return response_util(
                status="success",
                message=f"Sales Invoice created from Sales Order {sales_order_id}",
                http_status_code=201,
            )

    except frappe.ValidationError as ve:
        message = str(ve)
        if "credit limit has been crossed" in message.lower() or "extend the credit limits" in message.lower():
            return _handle_credit_limit_error(
                api, "credit_limit_exceeded", sales_order_id, so_doc, message
            )
        return _order_error(
            api,
            "validation_error",
            sales_order_id=sales_order_id,
            so_doc=so_doc,
            message="Validation error occurred while submitting Sales Invoice.",
            error=message,
            http_status_code=400,
        )

    except frappe.DoesNotExistError:
        return _order_error(
            api,
            "sales_order_not_found",
            sales_order_id=sales_order_id,
            message=f"Sales Order {sales_order_id} not found.",
            http_status_code=404,
        )

    except Exception as e:
        log_mobile_api_failure(
            api=api,
            step="unexpected_error",
            context=order_trace_context(sales_order_id=sales_order_id, so_doc=so_doc),
            error=e,
            http_status_code=500,
        )
        return response_util(
            status="error",
            message="Unexpected error while converting Sales Order to Sales Invoice.",
            error=str(e),
            http_status_code=500,
        )


@frappe.whitelist(allow_guest=True)
def convert_sales_order_to_invoice(sales_order_id=None):
    api = "convert_sales_order_to_invoice"
    so_doc = None
    try:
        if not sales_order_id:
            return _order_error(
                api,
                "missing_sales_order_id",
                sales_order_id=sales_order_id,
                message="sales_order_id parameter is required.",
                http_status_code=400,
            )

        with run_as_administrator_if_guest():
            so_doc = frappe.get_doc("Sales Order", sales_order_id)

            if so_doc.docstatus != 1:
                return _order_error(
                    api,
                    "sales_order_not_submitted",
                    sales_order_id=sales_order_id,
                    so_doc=so_doc,
                    message="Only submitted Sales Orders can be converted to Sales Invoices.",
                    http_status_code=400,
                )

            if not getattr(so_doc, "ref_practitioner", None):
                return _order_error(
                    api,
                    "missing_ref_practitioner",
                    sales_order_id=sales_order_id,
                    so_doc=so_doc,
                    message="Sales Order is missing Referring Practitioner which is required in the Sales Invoice.",
                    http_status_code=400,
                )

            for item in so_doc.items:
                if not item.rate or item.rate == 0:
                    return _order_error(
                        api,
                        "zero_item_rate",
                        sales_order_id=sales_order_id,
                        so_doc=so_doc,
                        message=f"Rate cannot be zero for item: {item.item_name} (Row: {item.idx})",
                        http_status_code=400,
                    )

            defaults = get_mobile_app_defaults()

            if not defaults.get("source_order"):
                return _order_error(
                    api,
                    "source_order_not_configured",
                    sales_order_id=sales_order_id,
                    so_doc=so_doc,
                    message="Mobile App Settings not configured. Please set Source Order.",
                    http_status_code=500,
                )

            si_doc = frappe.new_doc("Sales Invoice")
            si_doc.customer = so_doc.customer
            si_doc.patient = so_doc.patient
            si_doc.due_date = frappe.utils.nowdate()
            si_doc.selling_price_list = so_doc.selling_price_list
            si_doc.update_stock = 0
            si_doc.is_pos = 1
            si_doc.customer_address = so_doc.customer_address
            si_doc.shipping_address_name = so_doc.shipping_address_name
            si_doc.set_posting_time = 1
            si_doc.posting_date = frappe.utils.nowdate()
            si_doc.ref_practitioner = so_doc.ref_practitioner
            si_doc.cost_center = defaults["cost_center"]
            si_doc.source_order = defaults["source_order"]

            for item in so_doc.items:
                si_doc.append("items", {
                    "item_code": item.item_code,
                    "item_name": item.item_name,
                    "description": item.description,
                    "qty": item.qty,
                    "rate": item.rate,
                    "uom": item.uom,
                    "conversion_factor": item.conversion_factor,
                    "cost_center": defaults["cost_center"],
                    "so_detail": item.name,
                    "sales_order": so_doc.name,
                })

            si_doc.append("payments", {
                "mode_of_payment": defaults["mode_of_payment"],
                "amount": so_doc.rounded_total or so_doc.grand_total,
            })
            si_doc.insert(ignore_permissions=True)
            si_doc.submit()

            return response_util(
                status="success",
                message=f"Sales Invoice created from Sales Order {sales_order_id}",
                data={"invoice_id": si_doc.name},
                http_status_code=201,
            )

    except frappe.ValidationError as ve:
        message = str(ve)
        if "credit limit has been crossed" in message.lower() or "extend the credit limits" in message.lower():
            return _handle_credit_limit_error(
                api, "credit_limit_exceeded", sales_order_id, so_doc, message
            )
        return _order_error(
            api,
            "validation_error",
            sales_order_id=sales_order_id,
            so_doc=so_doc,
            message="Validation error occurred while submitting Sales Invoice.",
            error=message,
            http_status_code=400,
        )

    except frappe.DoesNotExistError:
        return _order_error(
            api,
            "sales_order_not_found",
            sales_order_id=sales_order_id,
            message=f"Sales Order {sales_order_id} not found.",
            http_status_code=404,
        )

    except Exception as e:
        log_mobile_api_failure(
            api=api,
            step="unexpected_error",
            context=order_trace_context(sales_order_id=sales_order_id, so_doc=so_doc),
            error=e,
            http_status_code=500,
        )
        return response_util(
            status="error",
            message="Unexpected error while converting Sales Order to Sales Invoice.",
            error=str(e),
            http_status_code=500,
        )


@frappe.whitelist(allow_guest=True)
def get_sales_orders_by_mobile(mobile=None):
    api = "get_sales_orders_by_mobile"
    try:
        if not mobile:
            return _order_error(
                api,
                "missing_mobile",
                mobile=mobile,
                message="Mobile number is required.",
                http_status_code=400,
            )

        with run_as_administrator_if_guest():
            patient_records = frappe.get_all(
                "Patient",
                filters={"mobile": mobile},
                fields=["name", "patient_name"],
            )
            if not patient_records:
                return _order_error(
                    api,
                    "no_patients_found",
                    mobile=mobile,
                    message=f"No patients found for mobile: {mobile}",
                    data=[],
                    http_status_code=404,
                )

            patient_name_map = {p["name"]: p["patient_name"] for p in patient_records}
            patient_ids = list(patient_name_map.keys())

            cutoff_date = frappe.utils.add_days(frappe.utils.today(), -90)

            sales_orders = frappe.get_all(
                "Sales Order",
                filters={"patient": ["in", patient_ids], "docstatus": 1, "creation": [">=", cutoff_date]},
                fields=[
                    "name", "transaction_date", "customer", "customer_group", "patient",
                    "grand_total", "status", "delivery_date", "contact_mobile",
                ],
                order_by="modified desc",
            )

            for so in sales_orders:
                so["items"] = frappe.get_all(
                    "Sales Order Item",
                    filters={"parent": so["name"]},
                    fields=["item_code", "item_name", "qty", "rate", "amount"],
                )
                so["patient_name"] = patient_name_map.get(so["patient"], "")

            return response_util(
                status="success",
                message="Sales Orders retrieved successfully",
                data=sales_orders,
                http_status_code=200,
            )

    except Exception as e:
        log_mobile_api_failure(
            api=api,
            step="unexpected_error",
            context=order_trace_context(mobile=mobile),
            error=e,
            http_status_code=500,
        )
        return response_util(
            status="error",
            message="Internal Server Error",
            error=str(e),
            http_status_code=500,
        )
