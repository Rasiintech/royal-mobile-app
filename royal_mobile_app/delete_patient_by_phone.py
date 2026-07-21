# apps/royal_mobile_app/royal_mobile_app/delete_patient_by_phone.py

import frappe

def delete_patients_by_phone(phone_number):
    """
    Finds and deletes patients matching the given mobile number,
    as well as their linked Customer records.
    """
    # 1. Fetch all patients matching the mobile number
    patients = frappe.get_all(
        "Patient", 
        filters={"mobile_no": phone_number}, 
        fields=["name", "customer"]
    )
    
    if not patients:
        print(f"⚠️ No patients found with Mobile No: {phone_number}")
        return

    print(f"🔍 Found {len(patients)} patient(s) associated with phone: {phone_number}\n")

    for patient in patients:
        patient_id = patient.get("name")
        customer_id = patient.get("customer")

        # 2. Delete the linked Customer first (to prevent integrity check failures)
        if customer_id and frappe.db.exists("Customer", customer_id):
            try:
                frappe.delete_doc("Customer", customer_id, ignore_permissions=True, force=True)
                print(f"✅ Deleted Customer: {customer_id}")
            except Exception as e:
                print(f"❌ Failed to delete Customer {customer_id}: {str(e)}")

        # 3. Delete the Patient record
        try:
            frappe.delete_doc("Patient", patient_id, ignore_permissions=True, force=True)
            print(f"✅ Deleted Patient: {patient_id}")
        except Exception as e:
            print(f"❌ Failed to delete Patient {patient_id}: {str(e)}")

    # 4. Commit changes permanently to the database
    frappe.db.commit()
    print("\n🚀 Database transaction successfully committed.")


# ==========================================
# CONFIGURATION: Change the phone number here
# ==========================================
TARGET_PHONE = "619379521"

# Run the execution function
delete_patients_by_phone(TARGET_PHONE)