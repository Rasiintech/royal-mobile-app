import frappe
from royal_mobile_app.utils.guest_api_utils import run_as_administrator_if_guest
from royal_mobile_app.utils.phone_utils import mobile_variants, normalize_somali_mobile
from royal_mobile_app.utils.response_utils import response_util
from royal_mobile_app.utils.trace_utils import log_mobile_api_failure, patient_trace_context


def _patient_error(api, step, mobile=None, patient_id=None, full_name=None, **kwargs):
	"""Log failure to Error Log and return standard error response (unchanged shape)."""
	log_mobile_api_failure(
		api=api,
		step=step,
		context=patient_trace_context(
			mobile=mobile,
			patient_id=patient_id,
			full_name=full_name,
			**(kwargs.get("extra_context") or {}),
		),
		message=kwargs.get("message"),
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


@frappe.whitelist(allow_guest=True)
def can_register_patient(full_name, mobile_number):
	api = "can_register_patient"
	if not all([full_name, mobile_number]):
		return _patient_error(
			api,
			"missing_required_params",
			mobile=mobile_number,
			full_name=full_name,
			message="Full name and mobile number are required.",
			http_status_code=400,
		)

	canonical = normalize_somali_mobile(mobile_number)
	if not canonical:
		return _patient_error(
			api,
			"invalid_mobile",
			mobile=mobile_number,
			full_name=full_name,
			message="Invalid mobile number format.",
			http_status_code=400,
		)

	try:
		variants = mobile_variants(canonical)
		with run_as_administrator_if_guest():
			exists = frappe.db.exists(
				"Patient",
				{"mobile_no": ["in", variants], "first_name": full_name},
			)
		if exists:
			return _patient_error(
				api,
				"patient_already_exists",
				mobile=canonical,
				full_name=full_name,
				patient_id=exists,
				message="This patient already exists.",
				http_status_code=409,
			)

		return response_util(
			status="success",
			message="Patient not exist You can register",
			data={"otp_sent": True},
			http_status_code=200,
		)
	except Exception as e:
		return _patient_error(
			api,
			"unexpected_error",
			mobile=canonical,
			full_name=full_name,
			message="An error occurred while checking patient registration.",
			error=e,
			http_status_code=500,
		)


@frappe.whitelist(allow_guest=True)
def patient_login(mobile_number):
	api = "patient_login"
	if not mobile_number:
		return _patient_error(
			api,
			"missing_mobile",
			mobile=mobile_number,
			message="Mobile number is required!",
			http_status_code=400,
		)

	canonical = normalize_somali_mobile(mobile_number)
	if not canonical:
		return _patient_error(
			api,
			"invalid_mobile",
			mobile=mobile_number,
			message="Invalid mobile number format.",
			http_status_code=400,
		)

	try:
		variants = mobile_variants(canonical)
		with run_as_administrator_if_guest():
			patient = frappe.get_value(
				"Patient",
				{"mobile_no": ["in", variants]},
				"name",
				order_by="creation asc",
			)

		if patient:
			with run_as_administrator_if_guest():
				patient_info = frappe.get_doc("Patient", patient)

			return response_util(
				status="success",
				message="Login successful",
				data={
					"patient_id": patient_info.name,
					"first_name": patient_info.first_name,
					"mobile": patient_info.mobile_no,
					"district": patient_info.territory,
					"age": patient_info.p_age,
					"Gender": patient_info.sex,
					"image": patient_info.get("image"),
				},
				http_status_code=200,
			)

		return _patient_error(
			api,
			"patient_not_found",
			mobile=canonical,
			message="Patient not found with the provided mobile number.",
			http_status_code=404,
		)

	except Exception as e:
		return _patient_error(
			api,
			"unexpected_error",
			mobile=canonical,
			message="An error occurred while logging in",
			error=e,
			http_status_code=500,
		)


@frappe.whitelist(allow_guest=True)
def register_patient(
	pat_full_name, pat_gender, pat_age, pat_age_type, pat_mobile_number, pat_district
):
	api = "register_patient"
	try:
		if not pat_full_name:
			return _patient_error(
				api,
				"missing_full_name",
				mobile=pat_mobile_number,
				full_name=pat_full_name,
				message="Full Name is required.",
				http_status_code=400,
			)

		canonical = normalize_somali_mobile(pat_mobile_number)
		if not canonical:
			return _patient_error(
				api,
				"invalid_mobile",
				mobile=pat_mobile_number,
				full_name=pat_full_name,
				message="Invalid mobile number format.",
				http_status_code=400,
			)

		variants = mobile_variants(canonical)
		with run_as_administrator_if_guest():
			existing = frappe.db.exists(
				"Patient",
				{"mobile_no": ["in", variants], "first_name": pat_full_name},
			)
			if existing:
				return _patient_error(
					api,
					"patient_already_exists",
					mobile=canonical,
					full_name=pat_full_name,
					patient_id=existing,
					message="This patient already exists.",
					http_status_code=409,
				)

			create_doc = frappe.new_doc("Patient")
			create_doc.first_name = pat_full_name
			create_doc.sex = pat_gender
			create_doc.p_age = pat_age
			create_doc.age_type = pat_age_type
			create_doc.mobile_no = canonical
			create_doc.territory = pat_district
			create_doc.how_did_you_hear_about_our_hospital = "Social Media"
			create_doc.insert()
			frappe.db.commit()

		if create_doc:
			return response_util(
				status="success",
				message="Patient registered successfully.",
				http_status_code=200,
			)

		return _patient_error(
			api,
			"registration_failed",
			mobile=canonical,
			full_name=pat_full_name,
			message="Patient registration failed.",
			http_status_code=404,
		)

	except Exception as e:
		return _patient_error(
			api,
			"unexpected_error",
			mobile=pat_mobile_number,
			full_name=pat_full_name,
			message="An error occurred while registering the patient.",
			error=e,
			http_status_code=500,
		)


@frappe.whitelist(allow_guest=True)
def get_patients_with_same_mobile(mobile_number, doctor_name=None):
	api = "get_patients_with_same_mobile"
	if not mobile_number:
		return _patient_error(
			api,
			"missing_mobile",
			mobile=mobile_number,
			message="Mobile number is required.",
			http_status_code=400,
		)

	canonical = normalize_somali_mobile(mobile_number)
	if not canonical:
		return _patient_error(
			api,
			"invalid_mobile",
			mobile=mobile_number,
			message="Invalid mobile number format.",
			http_status_code=400,
		)

	try:
		variants = mobile_variants(canonical)
		with run_as_administrator_if_guest():
			patients = frappe.get_all(
				"Patient",
				filters={"mobile_no": ["in", variants]},
				fields=[
					"name",
					"first_name",
					"p_age",
					"image",
					"customer_group",
					"creation",
				],
				order_by="creation asc",
			)

			if not patients:
				return _patient_error(
					api,
					"no_patients_found",
					mobile=canonical,
					message=f"No patients found for mobile number: {mobile_number}",
					extra_context={"doctor_name": doctor_name},
					http_status_code=404,
				)

			enriched_patients = []
			for patient in patients:
				patient_id = patient.get("name")
				patient["image"] = patient.get("image")
				patient["customer_group"] = (
					patient.get("customer_group") or "All Customer Groups"
				)

				fee_validity = frappe.get_all(
					"Fee Validity",
					filters={"patient": patient_id, "practitioner": doctor_name},
					fields=["name", "start_date", "valid_till", "status"],
					order_by="creation desc",
					limit_page_length=1,
				)

				if fee_validity:
					fee = fee_validity[0]
					patient["followupId"] = fee.get("name")
					patient["followupStartDate"] = fee.get("start_date")
					patient["followupExpirationDate"] = fee.get("valid_till")
					patient["followupStatus"] = fee.get("status")
				else:
					patient["followupId"] = None
					patient["followupStartDate"] = None
					patient["followupExpirationDate"] = None
					patient["followupStatus"] = None

				enriched_patients.append(
					{
						"name": patient["name"],
						"first_name": patient["first_name"],
						"p_age": patient["p_age"],
						"image": patient["image"],
						"customer_group": patient["customer_group"],
						"followupId": patient["followupId"],
						"followupStartDate": patient["followupStartDate"],
						"followupExpirationDate": patient["followupExpirationDate"],
						"followupStatus": patient["followupStatus"],
					}
				)

			return response_util(
				status="success",
				message="Patients found successfully.",
				data=enriched_patients,
				http_status_code=200,
			)

	except Exception as e:
		return _patient_error(
			api,
			"unexpected_error",
			mobile=canonical,
			message="An error occurred while retrieving patients.",
			error=e,
			extra_context={"doctor_name": doctor_name},
			http_status_code=500,
		)


@frappe.whitelist(allow_guest=True)
def get_patient_profile(patient_id, fcm_token=None):
	api = "get_patient_profile"
	try:
		with run_as_administrator_if_guest():
			patient_doc = frappe.get_doc("Patient", patient_id)

			if fcm_token and hasattr(patient_doc, "fcm_token"):
				if not patient_doc.fcm_token or patient_doc.fcm_token != fcm_token:
					patient_doc.fcm_token = fcm_token
					patient_doc.save(ignore_permissions=True)
					frappe.db.commit()

			return response_util(
				status="success",
				message="Patient profile retrieved successfully",
				data={
					"patient_id": patient_doc.name,
					"first_name": patient_doc.first_name,
					"gender": patient_doc.sex,
					"age": patient_doc.p_age,
					"mobile": patient_doc.mobile_no,
					"district": patient_doc.territory,
					"image": patient_doc.get("image"),
				},
				http_status_code=200,
			)

	except frappe.DoesNotExistError:
		return _patient_error(
			api,
			"patient_not_found",
			patient_id=patient_id,
			message=f"Patient with ID '{patient_id}' does not exist.",
			http_status_code=404,
		)
	except Exception as e:
		return _patient_error(
			api,
			"unexpected_error",
			patient_id=patient_id,
			message="An unexpected error occurred.",
			error=e,
			http_status_code=500,
		)


@frappe.whitelist(allow_guest=True)
def get_districts():
	api = "get_districts"
	try:
		with run_as_administrator_if_guest():
			districts = frappe.db.get_all("Territory", fields=["territory_name"])
		return response_util(
			status="success",
			message="Districts found successfully.",
			data=districts,
			http_status_code=200,
		)
	except Exception as e:
		return _patient_error(
			api,
			"unexpected_error",
			message="An error occurred while fetching districts.",
			error=e,
			http_status_code=500,
		)


@frappe.whitelist(allow_guest=True)
def get_all_departments():
	api = "get_all_departments"
	try:
		with run_as_administrator_if_guest():
			departments = frappe.db.get_all(
				"Department", fields=["name", "department_name"]
			)

		if not departments:
			return _patient_error(
				api,
				"no_departments_found",
				message="No departments found in the system.",
				http_status_code=404,
			)

		return response_util(
			status="success",
			message="Departments retrieved successfully.",
			data=departments,
			http_status_code=200,
		)

	except Exception as e:
		return _patient_error(
			api,
			"unexpected_error",
			message="An error occurred while retrieving departments.",
			error=e,
			http_status_code=500,
		)


@frappe.whitelist(allow_guest=True)
def submit_patient_feedback(
	patient_id,
	feedback_type,
	rating,
	comments=None,
	app_feedback_category=None,
	app_version=None,
	device_info=None,
):
	"""
	Submit patient feedback with proper validation and auto-naming
	Args:
		patient_id (str): Required - Patient document ID
		feedback_type (str): Required - From predefined options
		rating (float): Required - 1-5 scale
		comments (str): Optional - Feedback details
		app_feedback_category (str): Required if feedback_type is app related
		app_version (str): Optional - App version
		device_info (str): Optional - JSON string of device info
	Returns:
		dict: {'status': 'success/error', 'message': str, 'data': dict}
	"""
	api = "submit_patient_feedback"
	try:
		if not all([patient_id, feedback_type, rating]):
			return _patient_error(
				api,
				"missing_required_params",
				patient_id=patient_id,
				message="Patient ID, feedback type and rating are required",
				extra_context={
					"feedback_type": feedback_type,
					"rating": rating,
				},
				http_status_code=400,
			)

		valid_types = [
			"General Feedback",
			"Doctor Feedback",
			"Facility Feedback",
			"Appointment Feedback",
			"Service Feedback",
			"App Related Feedback",
		]
		if feedback_type not in valid_types:
			return _patient_error(
				api,
				"invalid_feedback_type",
				patient_id=patient_id,
				message=f"Invalid feedback type. Must be one of: {', '.join(valid_types)}",
				extra_context={"feedback_type": feedback_type},
				http_status_code=400,
			)

		try:
			rating = float(rating)
			if not (1 <= rating <= 5):
				raise ValueError
		except ValueError:
			return _patient_error(
				api,
				"invalid_rating",
				patient_id=patient_id,
				message="Rating must be a number between 1 and 5",
				extra_context={"rating": rating, "feedback_type": feedback_type},
				http_status_code=400,
			)

		if feedback_type == "App Related Feedback" and not app_feedback_category:
			return _patient_error(
				api,
				"missing_app_feedback_category",
				patient_id=patient_id,
				message="App feedback category is required for app-related feedback",
				extra_context={"feedback_type": feedback_type},
				http_status_code=400,
			)

		with run_as_administrator_if_guest():
			if not frappe.db.exists("Patient", patient_id):
				return _patient_error(
					api,
					"patient_not_found",
					patient_id=patient_id,
					message="Patient not found",
					extra_context={"feedback_type": feedback_type},
					http_status_code=404,
				)

			feedback = frappe.new_doc("Patient Feedback")
			feedback.update(
				{
					"patient": patient_id,
					"feedback_type": feedback_type,
					"rating": rating,
					"comments": comments,
					"status": "Open",
				}
			)

			if feedback_type == "App Related Feedback":
				feedback.update(
					{
						"app_feedback_category": app_feedback_category,
						"app_version": app_version or "1.0.0",
						"device_info": device_info or "{}",
					}
				)

			feedback.patient_name = frappe.db.get_value(
				"Patient", patient_id, "patient_name"
			)
			feedback.insert(ignore_permissions=True)
			frappe.db.commit()

			return response_util(
				status="success",
				message="Feedback submitted successfully",
				data={
					"feedback_id": feedback.name,
					"patient_name": feedback.patient_name,
					"submitted_on": feedback.creation,
				},
				http_status_code=201,
			)

	except Exception as e:
		return _patient_error(
			api,
			"unexpected_error",
			patient_id=patient_id,
			message="Failed to submit feedback",
			error=e,
			extra_context={"feedback_type": feedback_type, "rating": rating},
			http_status_code=500,
		)
