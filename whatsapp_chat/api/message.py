import frappe
import mimetypes



@frappe.whitelist()
def get_all(room: str, user_no: str = None):
    """Get all the messages of a particular room

    Args:
        room (str): Room's name.
        user_no (str, optional): User's mobile number. Derived from room if not provided.

    """
    if not user_no:
        user_no = frappe.db.get_value("WhatsApp Contact", room, "mobile_no")
        if not user_no:
            return []

    messages = frappe.db.sql("""
        SELECT creation,
        case
            when `to` <> '' then `to`
            else
            'Administrator'
        end as sender_user_no,
        case
            when COALESCE(content_type, 'text') = 'text' then COALESCE(message, '')
            else COALESCE(attach, message, '')
        end as content,
        case
            when COALESCE(content_type, 'text') <> 'text' then message
            else NULL
        end as caption,
        COALESCE(content_type, 'text') as content_type,
        COALESCE(message_type, '') as message_type,
        template,
        body_param
        from `tabWhatsApp Message` where (`to` = %(user_no)s or `from` = %(user_no)s)
        order by creation asc
    """, {"user_no": user_no}, as_dict=True)

    # Resolve template message content
    for msg in messages:
        if msg.get("message_type") == "Template" and msg.get("template"):
            if frappe.db.exists("WhatsApp Templates", msg["template"]):
                template_doc = frappe.get_cached_doc("WhatsApp Templates", msg["template"])
                template_text = template_doc.template or template_doc.template_name or msg["template"]

                # Substitute body parameters if available
                if msg.get("body_param"):
                    try:
                        import json
                        params = json.loads(msg["body_param"]) if isinstance(msg["body_param"], str) else msg["body_param"]
                        for key, value in params.items():
                            template_text = template_text.replace("{{" + key + "}}", str(value))
                    except Exception:
                        pass
                
                msg["content"] = template_text or f"[Template: {msg['template']}]"
            else:
                msg["content"] = f"[Template: {msg['template']}]"

    return messages


@frappe.whitelist()
def mark_as_read(room):
    """Mark messages as read in local DB and optionally send read receipts to WhatsApp."""
    try:
        # Update local contact status
        frappe.db.set_value("WhatsApp Contact", room, "is_read", 1, update_modified=False)
        frappe.db.commit()

        # Send read receipts to WhatsApp if enabled
        send_whatsapp_read_receipts(room)
    except Exception:
        pass  # Ignore concurrent update errors
    return "ok"


def send_whatsapp_read_receipts(room):
    """Send read receipts to WhatsApp for unread incoming messages."""
    try:
        # Get the contact's mobile number
        contact = frappe.get_doc("WhatsApp Contact", room)
        if not contact.mobile_no:
            return

        # Find unread incoming messages for this contact
        unread_messages = frappe.get_all(
            "WhatsApp Message",
            filters={
                "from": contact.mobile_no,
                "type": "Incoming",
                "status": ["not in", ["marked as read"]]
            },
            fields=["name", "whatsapp_account"],
            order_by="creation desc",
            limit=10
        )

        if not unread_messages:
            return

        # Check if auto read receipt is enabled for the account
        for msg in unread_messages:
            if not msg.whatsapp_account:
                continue

            allow_auto_read = frappe.db.get_value(
                "WhatsApp Account",
                msg.whatsapp_account,
                "allow_auto_read_receipt"
            )

            if allow_auto_read:
                try:
                    msg_doc = frappe.get_doc("WhatsApp Message", msg.name)
                    msg_doc.send_read_receipt()
                except Exception as e:
                    frappe.log_error(f"Failed to send read receipt for {msg.name}: {str(e)}", "WhatsApp Chat Read Receipt")
    except Exception as e:
        frappe.log_error(f"send_whatsapp_read_receipts error: {str(e)}", "WhatsApp Chat Read Receipt")



@frappe.whitelist()
def send(content, user, room, user_no, attachment=None):
    content_type = "text"
    if attachment:
        file_type = mimetypes.guess_type(content)[0]
        if file_type in ["image/apng","image/avif","image/gif","image/jpeg","image/png","image/svg","image/webp"]:
            content_type = 'image'
        elif file_type in ["application/pdf", "application/vnd.ms-powerpoint", "application/msword", "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/vnd.openxmlformats-officedocument.presentationml.presentation", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]:
            content_type = "document"
        elif file_type in ["audio/aac", "audio/mp4", "audio/mpeg", "audio/amr", "audio/ogg"]:
            content_type = 'audio'
        elif file_type in ["video/mp4", "video/3gp"]:
            content_type = "video"

        frappe.get_doc({
            "doctype": "WhatsApp Message",
            "to": user_no,
            "type": "Outgoing",
            "attach": content,
            "content_type": content_type
        }).save()
    else:
        frappe.get_doc({
            "doctype": "WhatsApp Message",
            "to": user_no,
            "type": "Outgoing",
            "message": content,
            "content_type": content_type
        }).save()

    return "ok"


def last_message(doc, method):
    if doc.type == 'Outgoing':
        mobile_no = doc.to
    else:
        mobile_no = doc.get("from")

    contact_name = frappe.db.get_value("WhatsApp Contact", filters={"mobile_no": mobile_no})
    if contact_name:
        # Use set_value to avoid "Document has been modified" conflicts when
        # the chatbot creates outgoing messages during incoming message processing.
        frappe.db.set_value("WhatsApp Contact", contact_name, {
            "last_message": doc.message,
            "is_read": 0
        })
        contact_data = frappe.db.get_value(
            "WhatsApp Contact", contact_name,
            ["name", "contact_name"], as_dict=True
        )
    else:
        chat_doc = frappe.get_doc({
            "doctype": "WhatsApp Contact",
            "mobile_no": mobile_no,
            "last_message": doc.message,
            "contact_name": doc.profile_name or mobile_no,
            "is_read": 0
        })
        chat_doc.save(ignore_permissions=True)
        contact_data = {"name": chat_doc.name, "contact_name": chat_doc.contact_name}

    # Resolve content — template messages have empty doc.message
    content = doc.message or doc.attach or ''
    if getattr(doc, 'message_type', None) == 'Template' and getattr(doc, 'template', None):
        try:
            if frappe.db.exists("WhatsApp Templates", doc.template):
                tpl = frappe.get_cached_doc("WhatsApp Templates", doc.template)
                content = tpl.template or tpl.template_name or doc.template
                if getattr(doc, 'body_param', None):
                    import json
                    params = json.loads(doc.body_param) if isinstance(doc.body_param, str) else doc.body_param
                    for key, value in params.items():
                        content = content.replace("{{" + key + "}}", str(value))
            else:
                content = f"[Template: {doc.template}]"
        except Exception:
            content = f"[Template: {doc.template}]"

    # Broadcast realtime updates for BOTH incoming and outgoing messages
    # so chatbot responses also appear in the chat UI.
    message_data = {
        "content": content,
        "creation": frappe.utils.now(),
        "room": contact_data["name"],
        "contact_name": contact_data.get("contact_name") or mobile_no,
        "sender_user_no": doc.to or '',
        "user": "Guest" if doc.type != 'Outgoing' else "System",
        "sent_by": frappe.session.user,
        "is_outgoing": doc.type == 'Outgoing'
    }

    users = frappe.get_all('User', filters={'enabled': 1, 'user_type': 'System User'}, fields=['name'])
    for user in users:
        if frappe.has_permission('WhatsApp Contact', ptype='read', user=user.name):
            frappe.publish_realtime(
                "latest_chat_updates",
                message_data,
                user=user.name
            )
            frappe.publish_realtime(
                contact_data["name"],
                message_data,
                user=user.name
            )

    return "ok"
