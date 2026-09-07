# apps/royal_mobile_app/royal_mobile_app/utils/trace_utils.py

import frappe


def log_mobile_api_failure(
	api,
	step,
	context=None,
	error=None,
	http_status_code=None,
	message=None,
):
	"""Write one Error Log row per API failure with a clear message + searchable context."""
	readable = (message or "").strip()
	if not readable and error is not None:
		readable = str(error).strip()
	if not readable:
		readable = f"Failure at step '{step}'"

	payload = {
		"message": readable,
		"api": api,
		"step": step,
		"http_status_code": http_status_code,
		"session_user": frappe.session.user,
		"context": {k: v for k, v in (context or {}).items() if v is not None},
	}
	if error is not None:
		payload["error"] = str(error)

	# Put readable text first so Error Log list/preview shows it clearly
	log_body = f"{readable}\n\n{frappe.as_json(payload, indent=2)}"
	if error is not None and not isinstance(error, str):
		log_body += "\n\n" + frappe.get_traceback()

	frappe.log_error(title=f"Mobile App API | {api} | {step}", message=log_body)


def appointment_trace_context(PID=None, doctor_practitioner=None, appointment_date=None, **extra):
	"""Build trace context for appointment APIs."""
	patient_mobile = None
	if PID and frappe.db.exists("Patient", PID):
		patient_mobile = frappe.db.get_value("Patient", PID, "mobile_no")

	return {
		"PID": PID,
		"patient_mobile": patient_mobile,
		"doctor_practitioner": doctor_practitioner,
		"appointment_date": appointment_date,
		**extra,
	}


def order_trace_context(sales_order_id=None, so_doc=None, mobile=None, **extra):
	"""Build trace context for order APIs."""
	context = {
		"sales_order_id": sales_order_id,
		"mobile": mobile,
	}
	if so_doc:
		context.update({
			"patient": getattr(so_doc, "patient", None),
			"customer": getattr(so_doc, "customer", None),
			"contact_mobile": getattr(so_doc, "contact_mobile", None),
		})
	context.update(extra)
	return context


def patient_trace_context(
	mobile=None,
	patient_id=None,
	full_name=None,
	**extra,
):
	"""Build trace context for patient APIs."""
	context = {
		"mobile": mobile,
		"patient_id": patient_id,
		"full_name": full_name,
	}
	context.update(extra)
	return {k: v for k, v in context.items() if v is not None}
