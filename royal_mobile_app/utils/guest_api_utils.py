"""Helpers for mobile app API methods whitelisted with allow_guest=True.

Document hooks and server scripts often call other whitelisted methods or check
permissions against the session user. Running those operations while temporarily
switching to Administrator avoids Guest permission failures while restoring the
original session user afterward.
"""

# apps/royal_mobile_app/royal_mobile_app/utils/guest_api_utils.py

from contextlib import contextmanager, nullcontext

import frappe


@contextmanager
def run_as_administrator():
    prev_user = frappe.session.user
    try:
        frappe.set_user("Administrator")
        yield
    finally:
        frappe.set_user(prev_user)


def run_as_administrator_if_guest():
    """Elevate session only when current user is Guest; no-op otherwise."""
    if frappe.session.user == "Guest":
        return run_as_administrator()
    return nullcontext()