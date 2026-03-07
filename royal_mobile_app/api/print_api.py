import frappe
import requests

@frappe.whitelist(allow_guest=True)
def call_external_api(que_name):
    url = "https://192.168.100.196:5000/print_que"  # Replace with your external API URL
  
  
    data = {
        "que_name":que_name,
    }

    # Sending POST request to the external API
    response = requests.post(url, json=data)

    # Handling the response
    if response.status_code == 200:
        result = response.json()
        return result
    else:
        return {"error": "Failed to call API", "status_code": response.status_code}
