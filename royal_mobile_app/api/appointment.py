import frappe
from royal_mobile_app.utils.guest_api_utils import run_as_administrator_if_guest
from royal_mobile_app.utils.response_utils import response_util
from royal_mobile_app.utils.trace_utils import (
    appointment_trace_context,
    log_mobile_api_failure,
)
from datetime import datetime
from royal_mobile_app.utils.erpnext_utils import get_mobile_app_defaults


def _count_que_appointments_for_doctor_on_date(practitioner, appointment_date):
    """Active Que rows (not cancelled) for this practitioner on this date (any source)."""
    return frappe.db.count(
        "Que",
        {"practitioner": practitioner, "date": appointment_date, "docstatus": ["<", 2]},
    )


def _get_effective_daily_limit(practitioner, defaults):
    """Doctor-level appointment_limit wins; fall back to global Mobile App Settings."""
    from frappe.utils import cint

    doctor_limit = cint(
        frappe.db.get_value("Healthcare Practitioner", practitioner, "appointment_limit") or 0
    )
    if doctor_limit > 0:
        return doctor_limit, "doctor"

    global_limit = cint(defaults.get("appointments_per_doctor_limit") or 0)
    return global_limit, "global"


def _appointment_error(api, step, PID, doctor_practitioner, appointment_date, **kwargs):
    """Log failure to Error Log and return standard error response (unchanged shape)."""
    log_mobile_api_failure(
        api=api,
        step=step,
        context=appointment_trace_context(PID, doctor_practitioner, appointment_date),
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


def _doctor_daily_limit_error(api, defaults, practitioner, appointment_date, PID, doctor_practitioner):
    """
    Enforce daily Que cap per practitioner: doctor appointment_limit, else global settings.
    Effective limit <= 0 means no cap (open-ended).
    """
    limit, limit_source = _get_effective_daily_limit(practitioner, defaults)
    if limit <= 0:
        return None
    current = _count_que_appointments_for_doctor_on_date(practitioner, appointment_date)
    if current >= limit:
        log_mobile_api_failure(
            api=api,
            step="doctor_daily_limit",
            context=appointment_trace_context(
                PID,
                doctor_practitioner,
                appointment_date,
                que_count=current,
                effective_limit=limit,
                limit_source=limit_source,
            ),
            http_status_code=400,
        )
        return response_util(
            status="error",
            message=(
                "This doctor has reached the daily appointment limit for this date. "
                "Please choose another date or doctor."
            ),
            http_status_code=400,
        )
    return None


def _appointment_cutoff_error(api, defaults, appointment_date, PID, doctor_practitioner):
    """
    Enforce appointment_end_time from Mobile App Settings for same-day bookings only.
    Future dates skip the time check; past dates are rejected.
    """
    from frappe.utils import getdate, get_time, nowdate, nowtime

    booking_date = getdate(appointment_date)
    today = getdate(nowdate())

    if booking_date < today:
        return _appointment_error(
            api,
            "appointment_past_date",
            PID,
            doctor_practitioner,
            appointment_date,
            message="Appointment date cannot be in the past.",
            http_status_code=400,
        )

    if booking_date > today:
        return None

    end_time = defaults.get("appointment_end_time")
    if not end_time:
        return None

    if get_time(nowtime()) >= get_time(end_time):
        return _appointment_error(
            api,
            "appointment_cutoff",
            PID,
            doctor_practitioner,
            appointment_date,
            message="Appointments for today are no longer accepted. Please choose another date.",
            http_status_code=400,
        )
    return None


def _future_appointments_error(api, defaults, appointment_date, PID, doctor_practitioner):
    """Reject future-date bookings when Enable Future Appointments is unchecked."""
    from frappe.utils import cint, getdate, nowdate

    if cint(defaults.get("enable_future_appointments")):
        return None
    if getdate(appointment_date) > getdate(nowdate()):
        return _appointment_error(
            api,
            "future_appointments_disabled",
            PID,
            doctor_practitioner,
            appointment_date,
            message="Future appointments are not available. Please choose today or contact the hospital.",
            http_status_code=400,
        )
    return None


def calculate_appointment_details(PID, doctor_practitioner, appointment_date):
    """Calculates pricing, type, and follow-up status in one place (DRY)."""
    appointment_date_obj = datetime.strptime(appointment_date, "%Y-%m-%d").date()
    customer_group = frappe.db.get_value("Patient", PID, "customer_group")
    doct_amount = (
        frappe.db.get_value("Healthcare Practitioner", doctor_practitioner, "op_consulting_charge")
        or 0
    )

    original_amount = float(doct_amount)
    payable_amount = original_amount
    appointment_type = "New Patient"
    is_follow_up = False

    fee_validity = frappe.get_all(
        "Fee Validity",
        filters={"patient": PID, "practitioner": doctor_practitioner, "status": "Pending"},
        fields=["valid_till", "visited", "max_visits"],
        order_by="valid_till desc",
        limit_page_length=1,
    )

    if fee_validity:
        fv = fee_validity[0]
        valid_till = datetime.strptime(str(fv["valid_till"]), "%Y-%m-%d").date()
        if appointment_date_obj <= valid_till and fv["visited"] < fv["max_visits"]:
            return 0, "Follow Up", True, original_amount

    if customer_group == "Membership":
        payable_amount = original_amount * 0.5

    return payable_amount, appointment_type, is_follow_up, original_amount


@frappe.whitelist(allow_guest=True)
def validate_appointment_booking(PID, doctor_practitioner, appointment_date):
    api = "validate_appointment_booking"
    try:
        if not all([PID, doctor_practitioner, appointment_date]):
            return _appointment_error(
                api,
                "missing_required_params",
                PID,
                doctor_practitioner,
                appointment_date,
                message="PID, Doctor Practitioner, and Appointment Date are required.",
                http_status_code=400,
            )

        with run_as_administrator_if_guest():
            if not frappe.db.exists("Patient", PID):
                return _appointment_error(
                    api,
                    "patient_not_found",
                    PID,
                    doctor_practitioner,
                    appointment_date,
                    message=f"Patient with ID {PID} does not exist.",
                    http_status_code=404,
                )

            if not frappe.db.exists("Healthcare Practitioner", doctor_practitioner):
                return _appointment_error(
                    api,
                    "doctor_not_found",
                    PID,
                    doctor_practitioner,
                    appointment_date,
                    message=f"Doctor {doctor_practitioner} does not exist.",
                    http_status_code=404,
                )

            if frappe.db.exists(
                "Que",
                {"patient": PID, "practitioner": doctor_practitioner, "date": appointment_date, "docstatus": ("<", 2)},
            ):
                return _appointment_error(
                    api,
                    "duplicate_appointment",
                    PID,
                    doctor_practitioner,
                    appointment_date,
                    message="An appointment for this patient with the same doctor on this date already exists.",
                    http_status_code=400,
                )

            defaults = get_mobile_app_defaults()

            future_err = _future_appointments_error(
                api, defaults, appointment_date, PID, doctor_practitioner
            )
            if future_err:
                return future_err

            cutoff_err = _appointment_cutoff_error(
                api, defaults, appointment_date, PID, doctor_practitioner
            )
            if cutoff_err:
                return cutoff_err

            limit_err = _doctor_daily_limit_error(
                api, defaults, doctor_practitioner, appointment_date, PID, doctor_practitioner
            )
            if limit_err:
                return limit_err

            payable_amount, appointment_type, is_follow_up, original_amount = calculate_appointment_details(
                PID, doctor_practitioner, appointment_date
            )

            temp_doc = frappe.new_doc("Que")
            temp_doc.update({
                "patient": PID,
                "practitioner": doctor_practitioner,
                "date": appointment_date,
                "paid_amount": payable_amount,
                "mode_of_payment": defaults["mode_of_payment"],
                "cost_center": defaults["cost_center"],
                "appointment_source": "Mobile App",
                "que_type": appointment_type,
                "follow_up": is_follow_up,
            })
            temp_doc.run_method("validate")

            customer_group = frappe.db.get_value("Patient", PID, "customer_group")

            return response_util(
                status="success",
                message="Patient is eligible to book appointment.",
                data={
                    "appointment_type": appointment_type,
                    "paid_amount": payable_amount,
                    "original_amount": original_amount,
                    "is_follow_up": is_follow_up,
                    "customer_group": customer_group,
                },
                http_status_code=200,
            )

    except frappe.ValidationError as ve:
        log_mobile_api_failure(
            api=api,
            step="que_validation_error",
            context=appointment_trace_context(PID, doctor_practitioner, appointment_date),
            error=ve,
            http_status_code=400,
        )
        return response_util(
            status="error",
            message="Validation failed during appointment simulation.",
            error=str(ve),
            http_status_code=400,
        )
    except Exception as e:
        log_mobile_api_failure(
            api=api,
            step="unexpected_error",
            context=appointment_trace_context(PID, doctor_practitioner, appointment_date),
            error=e,
            http_status_code=500,
        )
        return response_util(
            status="error",
            message="Unexpected error while validating appointment booking.",
            error=str(e),
            http_status_code=500,
        )


@frappe.whitelist(allow_guest=True)
def create_appointment(PID, doctor_practitioner, appointment_date):
    api = "create_appointment"
    try:
        if not all([PID, doctor_practitioner, appointment_date]):
            return _appointment_error(
                api,
                "missing_required_params",
                PID,
                doctor_practitioner,
                appointment_date,
                message="PID, Doctor Practitioner, and Appointment Date are required.",
                data=None,
                http_status_code=400,
            )

        with run_as_administrator_if_guest():
            defaults = get_mobile_app_defaults()
            if not defaults.get("cost_center") or not defaults.get("mode_of_payment"):
                return _appointment_error(
                    api,
                    "settings_not_configured",
                    PID,
                    doctor_practitioner,
                    appointment_date,
                    message="Mobile App Settings not configured. Please set Cost Center and Mode of Payment.",
                    data=None,
                    http_status_code=500,
                )

            if not frappe.db.exists("Patient", PID):
                return _appointment_error(
                    api,
                    "patient_not_found",
                    PID,
                    doctor_practitioner,
                    appointment_date,
                    message=f"Patient with ID {PID} does not exist.",
                    data=None,
                    http_status_code=404,
                )

            if not frappe.db.exists("Healthcare Practitioner", doctor_practitioner):
                return _appointment_error(
                    api,
                    "doctor_not_found",
                    PID,
                    doctor_practitioner,
                    appointment_date,
                    message=f"Doctor with ID {doctor_practitioner} does not exist.",
                    data=None,
                    http_status_code=404,
                )

            if frappe.db.exists(
                "Que",
                {"patient": PID, "practitioner": doctor_practitioner, "date": appointment_date, "docstatus": ("<", 2)},
            ):
                return _appointment_error(
                    api,
                    "duplicate_appointment",
                    PID,
                    doctor_practitioner,
                    appointment_date,
                    message="An appointment for this patient with the same doctor on this date already exists.",
                    http_status_code=400,
                )

            future_err = _future_appointments_error(
                api, defaults, appointment_date, PID, doctor_practitioner
            )
            if future_err:
                return future_err

            cutoff_err = _appointment_cutoff_error(
                api, defaults, appointment_date, PID, doctor_practitioner
            )
            if cutoff_err:
                return cutoff_err

            limit_err = _doctor_daily_limit_error(
                api, defaults, doctor_practitioner, appointment_date, PID, doctor_practitioner
            )
            if limit_err:
                return limit_err

            payable_amount, appointment_type, is_follow_up, original_amount = calculate_appointment_details(
                PID, doctor_practitioner, appointment_date
            )

            appointment = frappe.new_doc("Que")
            appointment.update({
                "patient": PID,
                "practitioner": doctor_practitioner,
                "date": appointment_date,
                "paid_amount": payable_amount,
                "mode_of_payment": defaults["mode_of_payment"],
                "cost_center": defaults["cost_center"],
                "appointment_source": "Mobile App",
                "que_type": appointment_type,
                "follow_up": is_follow_up,
            })

            appointment.insert()
            frappe.db.commit()

            return response_util(
                status="success",
                message="Appointment created successfully",
                data={
                    "appointment_id": appointment.name,
                    "appointment_type": appointment_type,
                    "amount_charged": payable_amount,
                    "original_amount": original_amount,
                },
                http_status_code=200,
            )

    except Exception as e:
        log_mobile_api_failure(
            api=api,
            step="unexpected_error",
            context=appointment_trace_context(PID, doctor_practitioner, appointment_date),
            error=e,
            http_status_code=500,
        )
        return response_util(
            status="error",
            message="An error occurred while creating the appointment.",
            error=str(e),
            data=None,
            http_status_code=500,
        )


@frappe.whitelist(allow_guest=True)
def get_appointments(mobile_no=None):
    api = "get_appointments"

    if not mobile_no:
        log_mobile_api_failure(
            api=api,
            step="missing_mobile",
            context={"mobile_no": mobile_no},
            http_status_code=400,
        )
        frappe.response['http_status_code'] = 400
        return {
            "status": "error",
            "msg": "Mobile No is required."
        }

    try:
        with run_as_administrator_if_guest():
            cutoff_date = frappe.utils.add_days(frappe.utils.today(), -90)

            appointments = frappe.get_all(
                "Que",
                filters={"mobile": mobile_no, "docstatus": ["<", 2], "date": [">=", cutoff_date]},
                fields=["name", "patient", "patient_name", "practitioner", "paid_amount", "date",
                        "appointment_source", "token_no"],
                order_by="date desc"
            )

            if not appointments:
                log_mobile_api_failure(
                    api=api,
                    step="no_appointments_found",
                    context={"mobile_no": mobile_no},
                    http_status_code=404,
                )
                frappe.response['http_status_code'] = 404
                return {
                    "status": "error",
                    "msg": f"No appointments found for patient: {mobile_no}",
                    "Data": None
                }

            frappe.response['http_status_code'] = 200
            return {
                "status": "success",
                "msg": "Appointments retrieved successfully",
                "Data": appointments
            }

    except Exception as e:
        log_mobile_api_failure(
            api=api,
            step="unexpected_error",
            context={"mobile_no": mobile_no},
            error=e,
            http_status_code=500,
        )
        frappe.response['http_status_code'] = 500
        return {
            "status": "error",
            "msg": "An error occurred while retrieving appointments.",
            "details": str(e)
        }
