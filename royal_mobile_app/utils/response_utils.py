import frappe

def response_util(status="success", message="", data=None, error=None, http_status_code=200):
    """
    Standardizes API responses.
    """
    frappe.response['http_status_code'] = http_status_code
    
    response = {
        "status": status,
        "msg": message,
        "Data": data,
    }
    
    if error:
        # response["error"] = str(error)
        response["details"] = str(error)
    
    return response