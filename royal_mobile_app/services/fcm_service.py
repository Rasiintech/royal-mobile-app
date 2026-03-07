import firebase_admin
from firebase_admin import credentials, messaging
from typing import Dict, List, Optional, Union
import frappe
from frappe.utils.background_jobs import enqueue
import json
import os
import re
from html import unescape
from frappe.utils import get_bench_id

# Debug Firebase Admin SDK version and capabilities
# def debug_firebase_admin():
    # """Debug function to check Firebase Admin SDK version and capabilities"""
    # try:
    #     import firebase_admin
    #     version = getattr(firebase_admin, '__version__', 'Unknown')
        
    #     # Check available messaging methods
    #     messaging_methods = [attr for attr in dir(messaging) if not attr.startswith('_')]
        
    #     debug_info = {
    #         "firebase_admin_version": version,
    #         "messaging_methods": messaging_methods,
    #         "has_send_multicast": hasattr(messaging, 'send_multicast'),
    #         "has_MulticastMessage": hasattr(messaging, 'MulticastMessage'),
    #         "python_path": os.sys.executable,
    #         "firebase_admin_path": firebase_admin.__file__
    #     }
        
    #     frappe.log_error("Firebase Admin Debug Info", json.dumps(debug_info, indent=2))
    #     return debug_info
    # except Exception as e:
    #     frappe.log_error("Firebase Admin Debug Failed", str(e))
    #     return {"error": str(e)}

class FCMService:
    MAX_TOKENS_PER_REQUEST = 500  # Firebase Admin SDK recommendation
    DEFAULT_PRIORITY = "high"
    FCM_TOKEN_REGEX = r'^[a-zA-Z0-9_\-:.]+$'

    def __init__(self, app_name: Optional[str] = None):
        """
        Initialize with specific app configuration
        Args:
            app_name: Name from FCM App Configuration table. 
                     If None, uses the default active config.
        """
        # Debug Firebase Admin SDK on initialization
        # debug_firebase_admin()
        
        self.settings = frappe.get_single("App Notification Settings")
        self.app_name = app_name
        self.fcm_config = self._get_specific_config()
        self.app = self._initialize_firebase_app()
        
        # Check if we have the modern API available
        self.has_send_multicast = hasattr(messaging, 'send_multicast')
        self.has_MulticastMessage = hasattr(messaging, 'MulticastMessage')
        
        if not self.has_send_multicast:
            frappe.log_error(
                "Firebase Admin SDK Warning", 
                "send_multicast not available. Using fallback method."
            )

    def _get_specific_config(self) -> Dict:
        """Get configuration for specified app or default active"""
        if not self.settings.push_enabled:
            frappe.throw("Push notifications are disabled in settings")
            
        if self.app_name:
            for config in self.settings.fcm_configurations:
                if config.app_name == self.app_name and config.is_active:
                    config_dict = self._config_to_dict(config)
                    if not config_dict.get("service_account_json"):
                        frappe.throw(f"Active config {self.app_name} has no service account file")
                    return config_dict
            frappe.throw(f"No active FCM config found for app: {self.app_name}")
            
        for config in self.settings.fcm_configurations:
            if config.is_active and config.default_app:
                config_dict = self._config_to_dict(config)
                if not config_dict.get("service_account_json"):
                    frappe.throw("Default FCM config has no service account file")
                return config_dict
                
        frappe.throw("No default FCM configuration found")

    def _config_to_dict(self, config) -> Dict:
        """Convert FCM config row to dictionary"""
        return {
            "service_account_json": config.service_account_json,
            "priority": config.priority or self.DEFAULT_PRIORITY,
            "sender_id": config.sender_id,
            "app_name": config.app_name
        }

    def _initialize_firebase_app(self):
        """Initialize Firebase app with credentials using the uploaded JSON file"""
        app_name = f"{self.fcm_config['app_name']}-{get_bench_id()}"  # Unique per bench
        
        try:
            return firebase_admin.get_app(app_name)
        except ValueError:
            json_file_url = self.fcm_config.get("service_account_json")
            if not json_file_url:
                frappe.throw("Firebase Service Account JSON file is not uploaded")
            
            try:
                file_doc = frappe.get_doc("File", {"file_url": json_file_url})
                json_file_path = file_doc.get_full_path()
                
                if not os.path.exists(json_file_path):
                    frappe.throw(f"Service account file not found at: {json_file_path}")
                
                if not file_doc.is_private:
                    frappe.log_error(
                        "Security Warning", 
                        f"Firebase credentials file {json_file_url} should be private!"
                    )
                
                with open(json_file_path) as json_file:
                    cred = credentials.Certificate(json.load(json_file))
                
                return firebase_admin.initialize_app(cred, name=app_name)
                
            except Exception as e:
                error_detail = {
                    "error": str(e),
                    "file_url": json_file_url,
                    "app_name": app_name,
                    "config": self.fcm_config
                }
                frappe.log_error(
                    title="Firebase Init Failed", 
                    message=json.dumps(error_detail, indent=2)
                )
                frappe.throw("Failed to initialize Firebase. Contact administrator.")

    def send(
        self,
        tokens: Union[str, List[str]],
        message: str,
        title: Optional[str] = None,
        data: Optional[Dict] = None,
        image: Optional[str] = None
    ) -> Dict:
        """
        Send push notification to device tokens using Firebase Admin SDK
        Uses send_multicast if available, falls back to individual sends
        """
        if isinstance(tokens, str):
            tokens = [tokens]
            
        if not tokens:
            return {"success": 0, "failure": 0, "message": "No tokens provided"}
            
        # Validate tokens before sending
        valid_tokens = [t for t in tokens if self._validate_token(t)]
        if not valid_tokens:
            return {"success": 0, "failure": len(tokens), "message": "No valid tokens provided"}
            
        token_chunks = [
            valid_tokens[i:i + self.MAX_TOKENS_PER_REQUEST] 
            for i in range(0, len(valid_tokens), self.MAX_TOKENS_PER_REQUEST)
        ]
        
        total_success = 0
        total_failure = 0
        batch_responses = []
        
        for chunk in token_chunks:
            if self.has_send_multicast and self.has_MulticastMessage:
                # Use modern API
                result = self._send_multicast_modern(chunk, message, title, data, image)
            else:
                # Use fallback method
                result = self._send_multicast_fallback(chunk, message, title, data, image)
            
            batch_responses.append(result)
            total_success += result.get("success_count", 0)
            total_failure += result.get("failure_count", 0)
        
        return {
            "success": total_success,
            "failure": total_failure,
            "responses": batch_responses,
            "app_name": self.app_name
        }

    # def _send_multicast_modern(self, tokens, message, title, data, image):
    #     """Send using modern send_multicast API"""
    #     try:
    #         message_obj = self._build_multicast_message(tokens, message, title, data, image)
    #         response = messaging.send_multicast(message_obj, app=self.app)
            
    #         # Log failures
    #         for idx, resp in enumerate(response.responses):
    #             if not resp.success:
    #                 error = resp.exception
    #                 frappe.log_error(
    #                     title="FCM Send Failure",
    #                     message=json.dumps({
    #                         "token": tokens[idx],
    #                         "error": str(error),
    #                         "title": title,
    #                         "data": data
    #                     }, indent=2)
    #                 )
            
    #         return {
    #             "success_count": response.success_count,
    #             "failure_count": response.failure_count,
    #             "method": "send_multicast"
    #         }
            
    #     except Exception as e:
    #         frappe.log_error(
    #             "FCM Send Failed",
    #             json.dumps({
    #                 "error": str(e),
    #                 "tokens": tokens,
    #                 "title": title,
    #                 "data": data,
    #                 "method": "send_multicast"
    #             }, indent=2)
    #         )
    #         return {
    #             "success_count": 0,
    #             "failure_count": len(tokens),
    #             "error": str(e),
    #             "method": "send_multicast"
    #         }
    
    def _send_multicast_modern(self, tokens: List[str], message: str, title: Optional[str], 
                         data: Optional[Dict], image: Optional[str]) -> Dict:
        """
        Send notifications using Firebase's modern multicast API.
        
        Args:
            tokens: List of device tokens
            message: Notification message body
            title: Notification title (optional)
            data: Additional data payload (optional)
            image: URL of notification image (optional)
            
        Returns:
            Dictionary with results including:
            - success_count: Number of successful sends
            - failure_count: Number of failed sends
            - method: API method used
            - errors: List of error details (if any)
        """
        try:
            # Build the multicast message
            message_obj = self._build_multicast_message(tokens, message, title, data, image)
            
            # Send the multicast message
            response = messaging.send_multicast(message_obj, app=self.app)
            
            # Process results
            errors = []
            for idx, resp in enumerate(response.responses):
                if not resp.success:
                    error_info = {
                        "token": tokens[idx],
                        "error": str(resp.exception),
                        "title": title,
                        "data": data
                    }
                    errors.append(error_info)
                    
                    # Log each failure
                    frappe.log_error(
                        title="FCM Send Failure",
                        message=json.dumps(error_info, indent=2)
                    )
            
            result = {
                "success_count": response.success_count,
                "failure_count": response.failure_count,
                "method": "send_multicast",
                "errors": errors if errors else None
            }
            
            # Log summary if there were failures
            if response.failure_count > 0:
                frappe.logger().info(
                    f"FCM multicast completed with {response.failure_count} failures out of {len(tokens)}"
                )
            
            return result
            
        except ValueError as ve:
            # Handle invalid arguments
            error_msg = f"Invalid FCM arguments: {str(ve)}"
            frappe.log_error("FCM Validation Error", error_msg)
            return {
                "success_count": 0,
                "failure_count": len(tokens),
                "error": error_msg,
                "method": "send_multicast"
            }
            
        except firebase_exceptions.FirebaseError as fe:
            # Handle Firebase-specific errors
            error_msg = f"Firebase error: {str(fe)}"
            frappe.log_error("FCM Firebase Error", error_msg)
            return {
                "success_count": 0,
                "failure_count": len(tokens),
                "error": error_msg,
                "method": "send_multicast"
            }
            
        except Exception as e:
            # Handle all other exceptions
            error_msg = f"Unexpected error: {str(e)}"
            frappe.log_error("FCM Unexpected Error", error_msg)
            return {
                "success_count": 0,
                "failure_count": len(tokens),
                "error": error_msg,
                "method": "send_multicast"
            }

    def _send_multicast_fallback(self, tokens, message, title, data, image):
        """Fallback method using individual send calls"""
        success_count = 0
        failure_count = 0
        
        for token in tokens:
            try:
                message_obj = self._build_single_message(token, message, title, data, image)
                response = messaging.send(message_obj, app=self.app)
                success_count += 1
                
            except Exception as e:
                failure_count += 1
                frappe.log_error(
                    title="FCM Send Failure (Fallback)",
                    message=json.dumps({
                        "token": token,
                        "error": str(e),
                        "title": title,
                        "data": data
                    }, indent=2)
                )
        
        return {
            "success_count": success_count,
            "failure_count": failure_count,
            "method": "send_fallback"
        }

    def _validate_token(self, token: str) -> bool:
        """Validate FCM token format"""
        if not token or not re.match(self.FCM_TOKEN_REGEX, token):
            frappe.log_error("Invalid FCM Token", f"Token: {token}")
            return False
        return True
    
    def _clean_message_text(self, text: str) -> str:
        """Remove HTML tags and convert HTML entities to plain text"""
        if not text:
            return text
            
        # First unescape HTML entities (like &amp; -> &)
        text = unescape(text)
        
        # Then remove HTML tags
        clean_text = re.sub(r'<[^>]+>', '', text)
        
        # Optionally clean up multiple spaces
        clean_text = ' '.join(clean_text.split())
        
        return clean_text

    def _build_multicast_message(self, tokens, message, title, data, image):
        """Build Firebase MulticastMessage object (modern API)"""
        priority = self.fcm_config.get("priority", self.DEFAULT_PRIORITY)
        
        # Clean message text
        clean_message = self._clean_message_text(message)
        clean_title = self._clean_message_text(title) if title else None
        
        # Clean data dictionary to ensure all values are strings
        cleaned_data = {}
        if data:
            cleaned_data = {
                k: str(v) if v is not None else "" 
                for k, v in data.items()
            }
            
        # Get the final image URL
        notification_image = self._get_notification_image(image)    

        notification = messaging.Notification(
            title=clean_title or "Notification",
            body=clean_message,
            image=notification_image
        )

        android_config = messaging.AndroidConfig(
            priority="high" if priority == "high" else "normal",
            notification=messaging.AndroidNotification(
                image=notification_image  # Android-specific image setting
            )
        )

        apns_config = messaging.APNSConfig(
            headers={"apns-priority": "10" if priority == "high" else "5"},
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    mutable_content=True  # Required for iOS to display images
                )
            ),
            fcm_options=messaging.APNSFCMOptions(
                image=notification_image  # iOS-specific image setting
            )
        )

        return messaging.MulticastMessage(
            notification=notification,
            data=cleaned_data,  # Use cleaned_data instead of original data
            tokens=tokens,
            android=android_config,
            apns=apns_config
        )

    def _build_single_message(self, token, message, title, data, image):
        """Build Firebase Message object for single token (fallback API)"""
        priority = self.fcm_config.get("priority", self.DEFAULT_PRIORITY)
        
        # Clean message text
        clean_message = self._clean_message_text(message)
        clean_title = self._clean_message_text(title) if title else None
        
        # Clean data dictionary to ensure all values are strings
        cleaned_data = {}
        if data:
            cleaned_data = {
                k: str(v) if v is not None else "" 
                for k, v in data.items()
            }
            
        # Get the final image URL
        notification_image = self._get_notification_image(image)    

        notification = messaging.Notification(
            title=clean_title or "Notification",
            body=clean_message,
            image=notification_image
        )

        android_config = messaging.AndroidConfig(
            priority="high" if priority == "high" else "normal",
            notification=messaging.AndroidNotification(
                image=notification_image  # Android-specific image setting
            )
        )

        apns_config = messaging.APNSConfig(
            headers={"apns-priority": "10" if priority == "high" else "5"},
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    mutable_content=True  # Required for iOS to display images
                )
            ),
            fcm_options=messaging.APNSFCMOptions(
                image=notification_image  # iOS-specific image setting
            )
        )

        return messaging.Message(
            notification=notification,
            data=cleaned_data,  # Use cleaned_data instead of original data
            token=token,
            android=android_config,
            apns=apns_config
        )

    def send_async(
        self,
        tokens: Union[str, List[str]],
        message: str,
        title: Optional[str] = None,
        data: Optional[Dict] = None,
        image: Optional[str] = None
    ):
        """Queue push notification for background sending"""
        enqueue(
            method=self.send,
            queue="short",
            timeout=300,  # 5 minutes
            tokens=tokens,
            message=message,
            title=title,
            data=data,
            image=image,
            job_name=f"FCM Notification - {title or 'No Title'}"
        )
        
    def _get_notification_image(self, image):
        """Process image input to return a valid URL for FCM"""
        if not image:
            return None
        
        # If it's already a URL (starts with http)
        if isinstance(image, str) and image.startswith(('http://', 'https://')):
            return image
        
        # If it's a file path/attachment
        try:
            # Check if it's a Frappe file URL
            if image.startswith('/files/'):
                file_doc = frappe.get_doc("File", {"file_url": image})
                if file_doc.is_private:
                    # For private files, you'll need to generate a signed URL
                    # This requires additional implementation based on your storage setup
                    frappe.log_error(
                        "Notification Image Warning",
                        "Private file attachments require signed URLs for notifications"
                    )
                    return None
                return frappe.utils.get_url(image)
            
            # Handle other cases if needed
            return frappe.utils.get_url(image)
        except Exception as e:
            frappe.log_error("Notification Image Processing Failed", str(e))
            return None    

    def subscribe_to_topic(self, tokens: Union[str, List[str]], topic_name: str) -> Dict:
        """Subscribe devices to a topic using Firebase Admin SDK"""
        return self._topic_operation(tokens, topic_name, "subscribe")

    def unsubscribe_from_topic(self, tokens: Union[str, List[str]], topic_name: str) -> Dict:
        """Unsubscribe devices from a topic using Firebase Admin SDK"""
        return self._topic_operation(tokens, topic_name, "unsubscribe")

    def _topic_operation(self, tokens: Union[str, List[str]], topic_name: str, operation: str) -> Dict:
        """Internal method for topic subscription management"""
        if isinstance(tokens, str):
            tokens = [tokens]

        if not tokens:
            return {"success": False, "message": "No tokens provided"}

        if not topic_name or not isinstance(topic_name, str):
            return {"success": False, "message": "Invalid topic name"}

        try:
            if operation == "subscribe":
                response = messaging.subscribe_to_topic(tokens, topic_name, app=self.app)
            else:
                response = messaging.unsubscribe_from_topic(tokens, topic_name, app=self.app)

            return {
                "success": True,
                "results": {
                    "success_count": response.success_count,
                    "failure_count": response.failure_count,
                    "errors": [str(e) for e in response.errors] if response.errors else None
                },
                "topic": topic_name,
                "operation": operation,
                "tokens_processed": len(tokens)
            }
        except Exception as e:
            frappe.log_error("FCM Topic Operation Failed", str(e))
            return {
                "success": False,
                "error": str(e),
                "topic": topic_name,
                "operation": operation
            }

    def send_to_topic(self,
               topic_name: str,
               message: str,
               title: Optional[str] = None,
               data: Optional[Dict] = None,
               image: Optional[str] = None) -> Dict:
        """Send message to a topic using Firebase Admin SDK"""
        if not topic_name or not isinstance(topic_name, str):
            return {"success": False, "message": "Invalid topic name"}

        try:
            # Clean title and message from HTML tags/entities
            clean_message = self._clean_message_text(message)
            clean_title = self._clean_message_text(title) if title else "Notification"
            
            # Get the final image URL
            notification_image = self._get_notification_image(image)

            message_obj = messaging.Message(
                notification=messaging.Notification(
                    title=clean_title,
                    body=clean_message,
                    image=notification_image
                ),
                data=data or {},
                topic=topic_name,
                android=messaging.AndroidConfig(
                    priority="high" if self.fcm_config["priority"] == "high" else "normal",
                    notification=messaging.AndroidNotification(
                        image=notification_image
                    )
                ),
                apns=messaging.APNSConfig(
                    headers={
                        "apns-priority": "10" if self.fcm_config["priority"] == "high" else "5"
                    },
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            mutable_content=True
                        )
                    ),
                    fcm_options=messaging.APNSFCMOptions(
                        image=notification_image
                    )
                )
            )

            response = messaging.send(message_obj, app=self.app)
            return {
                "success": True,
                "message_id": response,
                "topic": topic_name
            }

        except Exception as e:
            frappe.log_error("FCM Topic Send Failed", str(e))
            return {
                "success": False,
                "error": str(e),
                "topic": topic_name
            }

    def send_to_topic_async(self,
                          topic_name: str,
                          message: str,
                          title: Optional[str] = None,
                          data: Optional[Dict] = None,
                          image: Optional[str] = None):
        """Queue topic message for background sending"""
        enqueue(
            method=self.send_to_topic,
            queue="short",
            topic_name=topic_name,
            message=message,
            title=title,
            data=data,
            image=image
        )

    def __del__(self):
        """Cleanup Firebase app when instance is destroyed"""
        if hasattr(self, 'app'):
            try:
                firebase_admin.delete_app(self.app)
            except Exception as e:
                frappe.log_error("Firebase App Cleanup Failed", str(e))
