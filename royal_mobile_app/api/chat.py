# frappe-bench/apps/royal_mobile_app/royal_mobile_app/api/chat.py

import frappe
import json
from frappe import whitelist
from frappe.utils import now_datetime

@whitelist(allow_guest=False)
def send_message():
    """Send a chat message"""
    try:
        # Get request data from form data or JSON
        if frappe.request.method == 'POST':
            if frappe.request.content_type and 'application/json' in frappe.request.content_type:
                data = frappe.local.form_dict
            else:
                data = frappe.form_dict
        else:
            frappe.response['http_status_code'] = 405
            return {
                "status": "error",
                "message": "Method not allowed"
            }
        
        # Validate required fields
        required_fields = ['sender', 'sender_type', 'receiver', 'receiver_type', 'message']
        for field in required_fields:
            if field not in data or not data[field]:
                frappe.response['http_status_code'] = 400
                return {
                    "status": "error",
                    "message": f"{field.replace('_', ' ').title()} is required"
                }
        
        # Create message document
        doc = frappe.new_doc("Chat Message")
        doc.sender = data['sender']
        doc.sender_type = data['sender_type']
        doc.receiver = data['receiver']
        doc.receiver_type = data['receiver_type']
        doc.message = data['message']
        
        # Optional fields
        if 'seen' in data:
            doc.seen = data['seen']
        if 'attachment' in data:
            doc.attachment = data['attachment']
        if 'timestamp' in data:
            doc.timestamp = data['timestamp']
            
        doc.insert(ignore_permissions=True)
        
        frappe.response['http_status_code'] = 201
        return {
            "status": "success",
            "message": "Message sent successfully",
            "message_id": doc.name
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Send Message Error")
        frappe.response['http_status_code'] = 500
        return {
            "status": "error",
            "message": "Failed to send message",
            "error": str(e)
        }

@whitelist(allow_guest=False)
def get_messages():
    """Get message history between two users"""
    try:
        # Get request data
        if frappe.request.method == 'POST':
            if frappe.request.content_type and 'application/json' in frappe.request.content_type:
                data = frappe.local.form_dict
            else:
                data = frappe.form_dict
        else:
            data = frappe.form_dict
        
        # Validate required fields
        if 'user1' not in data or 'user2' not in data:
            frappe.response['http_status_code'] = 400
            return {
                "status": "error",
                "message": "user1 and user2 parameters are required"
            }
        
        user1 = data['user1']
        user2 = data['user2']
        page = int(data.get('page', 0))
        page_size = int(data.get('page_size', 20))
        
        # Get messages between the two users
        messages = frappe.get_all("Chat Message",
            filters={
                "sender": ["in", [user1, user2]],
                "receiver": ["in", [user1, user2]]
            },
            fields=["name", "sender", "sender_type", "receiver", "receiver_type", 
                   "message", "timestamp", "seen", "attachment", "amended_from"],
            order_by="timestamp desc",
            start=page * page_size,
            page_length=page_size
        )
        
        # Mark messages as read for the current user if specified
        current_user = data.get('current_user')
        mark_read = data.get('mark_read', 'false').lower() == 'true'
        
        if current_user and mark_read:
            frappe.db.sql("""
                UPDATE `tabChat Message` 
                SET seen = 1 
                WHERE receiver = %s AND sender = %s AND seen = 0
            """, (current_user, user2 if current_user == user1 else user1))
            frappe.db.commit()
        
        frappe.response['http_status_code'] = 200
        return {
            "status": "success",
            "messages": messages,
            "page": page,
            "page_size": page_size,
            "total_count": len(messages)
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Messages Error")
        frappe.response['http_status_code'] = 500
        return {
            "status": "error",
            "message": "Failed to retrieve messages",
            "error": str(e)
        }

@whitelist(allow_guest=False)
def get_chat_contacts():
    """Get list of doctors/patients the user can chat with"""
    try:
        # Get request data
        if frappe.request.method == 'POST':
            if frappe.request.content_type and 'application/json' in frappe.request.content_type:
                data = frappe.local.form_dict
            else:
                data = frappe.form_dict
        else:
            data = frappe.form_dict
        
        if 'user_id' not in data or 'user_type' not in data:
            frappe.response['http_status_code'] = 400
            return {
                "status": "error",
                "message": "user_id and user_type parameters are required"
            }
        
        user_id = data['user_id']
        user_type = data['user_type']
        contacts = []
        
        if user_type == "Patient":
            # Patients can chat with all doctors
            doctors = frappe.get_all("Healthcare Practitioner",
                fields=["name", "first_name", "last_name", "speciality", "department", "image"]
            )
            
            for doctor in doctors:
                contacts.append({
                    "id": doctor.name,
                    "name": f"Dr. {doctor.first_name} {doctor.last_name}",
                    "type": "Doctor",
                    "speciality": doctor.speciality,
                    "department": doctor.department,
                    "image": doctor.image
                })
                
        else:  # Doctor or other user type
            # Doctors can chat with all patients
            patients = frappe.get_all("Patient",
                fields=["name", "first_name", "last_name", "mobile_no", "image"]
            )
            
            for patient in patients:
                contacts.append({
                    "id": patient.name,
                    "name": f"{patient.first_name} {patient.last_name}",
                    "type": "Patient",
                    "mobile": patient.mobile_no,
                    "image": patient.image
                })
        
        # Get last message and unread count for each contact
        for contact in contacts:
            last_message = frappe.get_all("Chat Message",
                filters={
                    "sender": ["in", [user_id, contact['id']]],
                    "receiver": ["in", [user_id, contact['id']]]
                },
                fields=["message", "timestamp", "sender", "seen"],
                order_by="timestamp desc",
                limit=1
            )
            
            unread_count = frappe.db.count("Chat Message", {
                "sender": contact['id'],
                "receiver": user_id,
                "seen": 0
            })
            
            contact["last_message"] = last_message[0] if last_message else None
            contact["unread_count"] = unread_count
        
        frappe.response['http_status_code'] = 200
        return {
            "status": "success",
            "contacts": contacts
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Chat Contacts Error")
        frappe.response['http_status_code'] = 500
        return {
            "status": "error",
            "message": "Failed to retrieve chat contacts",
            "error": str(e)
        }

@whitelist(allow_guest=False)
def mark_messages_as_read():
    """Mark messages as read"""
    try:
        # Get request data
        if frappe.request.method == 'POST':
            if frappe.request.content_type and 'application/json' in frappe.request.content_type:
                data = frappe.local.form_dict
            else:
                data = frappe.form_dict
        else:
            data = frappe.form_dict
        
        if 'user_id' not in data or 'contact_id' not in data:
            frappe.response['http_status_code'] = 400
            return {
                "status": "error",
                "message": "user_id and contact_id parameters are required"
            }
        
        frappe.db.sql("""
            UPDATE `tabChat Message` 
            SET seen = 1 
            WHERE receiver = %s AND sender = %s AND seen = 0
        """, (data['user_id'], data['contact_id']))
        frappe.db.commit()
        
        frappe.response['http_status_code'] = 200
        return {
            "status": "success",
            "message": "Messages marked as read"
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Mark Messages Read Error")
        frappe.response['http_status_code'] = 500
        return {
            "status": "error",
            "message": "Failed to mark messages as read",
            "error": str(e)
        }

@whitelist(allow_guest=False)
def get_unread_count():
    """Get unread message count for a user"""
    try:
        # Get request data
        if frappe.request.method == 'POST':
            if frappe.request.content_type and 'application/json' in frappe.request.content_type:
                data = frappe.local.form_dict
            else:
                data = frappe.form_dict
        else:
            data = frappe.form_dict
        
        if 'user_id' not in data:
            frappe.response['http_status_code'] = 400
            return {
                "status": "error",
                "message": "user_id parameter is required"
            }
        
        user_id = data['user_id']
        
        unread_count = frappe.db.count("Chat Message", {
            "receiver": user_id,
            "seen": 0
        })
        
        frappe.response['http_status_code'] = 200
        return {
            "status": "success",
            "unread_count": unread_count
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Unread Count Error")
        frappe.response['http_status_code'] = 500
        return {
            "status": "error",
            "message": "Failed to get unread count",
            "error": str(e)
        }