import frappe



@frappe.whitelist()
def create(contact_name, mobile_no, email):
    """Create contact."""
    frappe.get_doc({
        "doctype": "WhatsApp Contact",
        "contact_name": contact_name,
        "mobile_no": mobile_no,
        "email": email
    }).save()
    return "email"


@frappe.whitelist()
def get(email=None):
    """Get all contacts (Shared Inbox)"""
    return frappe.db.get_all(
        "WhatsApp Contact",
        fields=["*"])


@frappe.whitelist()
def resolve_contacts():
    """Backfill existing WhatsApp Contacts by linking them to matching Frappe Contacts.

    Searches for unlinked WhatsApp Contacts and tries to match them
    to Frappe Contacts by phone number. Updates contact link and contact_name.
    """
    from whatsapp_chat.whatsapp_chat.doctype.whatsapp_contact.whatsapp_contact import (
        find_contact_by_phone,
    )

    unlinked = frappe.get_all(
        "WhatsApp Contact",
        filters={"contact": ["is", "not set"]},
        fields=["name", "mobile_no"],
    )

    updated = 0
    for wa_contact in unlinked:
        contact_name, full_name = find_contact_by_phone(wa_contact.mobile_no)
        if contact_name:
            values = {"contact": contact_name}
            if full_name:
                values["contact_name"] = full_name
            frappe.db.set_value("WhatsApp Contact", wa_contact.name, values)
            updated += 1

    frappe.db.commit()
    return {"updated": updated, "total": len(unlinked)}


def sync_contact_name(doc, method):
    """Hook called on Contact on_update. Syncs full_name to linked WhatsApp Contacts."""
    full_name = doc.full_name or doc.first_name
    if not full_name:
        return

    linked = frappe.get_all(
        "WhatsApp Contact",
        filters={"contact": doc.name},
        fields=["name"],
    )
    for wa_contact in linked:
        frappe.db.set_value(
            "WhatsApp Contact", wa_contact.name, "contact_name", full_name
        )

