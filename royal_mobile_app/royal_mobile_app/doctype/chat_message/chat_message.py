# Copyright (c) 2025, rasiin and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document

class ChatMessage(Document):
	pass

#  frappe-bench/apps/medical_app/medical_app/medical_app/doctype/chat_message/chat_message.py

# import frappe
# from frappe.model.document import Document
# from frappe_socketio import send_message as socket_send


# class ChatMessage(Document):
#     def before_save(self):
#         if not self.timestamp:
#             self.timestamp = frappe.utils.now_datetime()
    
#     def after_insert(self):
#         # Send real-time update via SocketIO
#         # Send real-time update
#         self.send_real_time_update()
#         # Store in delivery queue for confirmation
#         self.add_to_delivery_queue()
    
#     def send_real_time_update(self):
#         try:
#             room_id = f"chat_{min(self.sender, self.receiver)}_{max(self.sender, self.receiver)}"
            
#             socket_send("new_message", {
#                 "name": self.name,
#                 "sender": self.sender,
#                 "sender_type": self.sender_type,
#                 "receiver": self.receiver,
#                 "receiver_type": self.receiver_type,
#                 "message": self.message,
#                 "seen": self.seen,
#                 "attachment": self.attachment,
#                 "timestamp": str(self.timestamp) if self.timestamp else None,
#                 "amended_from": self.amended_from
#             }, room=room_id)
#         except ImportError:
#             frappe.log_error("SocketIO not installed", "Chat Message Real-time Error")
#         except Exception as e:
#             frappe.log_error(f"SocketIO Error: {str(e)}", "Chat Message Real-time Error")
            
#     def add_to_delivery_queue(self):
#         """Add message to delivery queue for confirmation"""
#         delivery_doc = frappe.new_doc("Message Delivery Queue")
#         delivery_doc.message_id = self.name
#         delivery_doc.sender = self.sender
#         delivery_doc.receiver = self.receiver
#         delivery_doc.insert(ignore_permissions=True)         