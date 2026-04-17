# WhatsApp Contact to Frappe Contact Linking

## Problem

The WhatsApp Chat widget displayed raw phone numbers instead of contact names. When a new WhatsApp message arrived from an unknown number, the system created a `WhatsApp Contact` record with `contact_name` set to the phone number (e.g., `919876543210`). There was no connection between the `WhatsApp Contact` doctype (used by the chat UI) and Frappe's standard `Contact` doctype (which stores customer/supplier names and phone numbers).

### Before (Data Model)

```
Frappe Contact (standard)
    |-- first_name, full_name
    |-- phone_nos (child table: Contact Phone)
    |-- mobile_no
    X  (no connection)
WhatsApp Contact (whatsapp_chat)
    |-- contact_name  --> often just "919876543210"
    |-- mobile_no     --> "919876543210"
```

### After (Data Model)

```
Frappe Contact (standard)
    |-- first_name, full_name
    |-- phone_nos (child table: Contact Phone)
    |-- mobile_no
    |
    v  (linked via `contact` field)
WhatsApp Contact (whatsapp_chat)
    |-- contact       --> Link to "Contact" doctype
    |-- contact_name  --> "John Doe" (resolved from Contact)
    |-- mobile_no     --> "919876543210"
```

---

## What Changed

### 1. New `contact` Link Field on WhatsApp Contact

**File:** `whatsapp_chat/whatsapp_chat/doctype/whatsapp_contact/whatsapp_contact.json`

A new `Link` field was added to the `WhatsApp Contact` doctype that points to Frappe's standard `Contact` doctype. This field stores the reference to the matched contact record.

```json
{
  "fieldname": "contact",
  "fieldtype": "Link",
  "label": "Contact",
  "options": "Contact"
}
```

**Field order:** `contact_name`, `contact`, `mobile_no`, `is_read`, `last_message`, `email`

---

### 2. Automatic Contact Resolution on Creation

**File:** `whatsapp_chat/whatsapp_chat/doctype/whatsapp_contact/whatsapp_contact.py`

Two module-level utility functions and a `before_insert` hook were added.

#### `_normalize_phone(number)`

Strips all non-digit characters from a phone number and returns the last 10 digits for comparison. This handles format variations like `+919876543210`, `919876543210`, `91 98765 43210`, and `9876543210`.

```python
_normalize_phone("+91 98765 43210")  # returns "9876543210"
_normalize_phone("919876543210")      # returns "9876543210"
_normalize_phone("9876543210")        # returns "9876543210"
```

#### `find_contact_by_phone(mobile_no)`

Searches for a matching Frappe `Contact` by phone number using a two-step lookup:

1. **Contact Phone child table** -- Queries `tabContact Phone` joined with `tabContact` where the phone number (stripped of `+` and spaces) ends with the same last 10 digits.
2. **Contact.mobile_no fallback** -- If no match in the child table, queries the `mobile_no` field directly on `tabContact`.

Returns a tuple of `(contact_name, full_name)` or `(None, None)` if no match is found.

**SQL matching strategy:**
```sql
WHERE REPLACE(REPLACE(cp.phone, '+', ''), ' ', '') LIKE '%9876543210'
```

#### `before_insert` Hook

When a new `WhatsApp Contact` is created (triggered by an incoming WhatsApp message), the `resolve_contact()` method runs automatically:

1. If `self.contact` is already set, skip (no override).
2. Call `find_contact_by_phone(self.mobile_no)`.
3. If a match is found, set `self.contact` to the Contact record name and `self.contact_name` to the Contact's `full_name`.

This means the chat UI immediately shows the real contact name instead of a phone number.

---

### 3. WhatsApp Profile Name as Fallback

**File:** `whatsapp_chat/api/message.py`

**Function:** `last_message()` (line 184)

Previously, when creating a new `WhatsApp Contact` for an unknown number, the `contact_name` was always set to the raw phone number:

```python
# Before
"contact_name": mobile_no,

# After
"contact_name": doc.profile_name or mobile_no,
```

Now the name resolution priority is:

| Priority | Source | Example |
|----------|--------|---------|
| 1 | Frappe Contact `full_name` | "John Doe" (set by `before_insert`) |
| 2 | WhatsApp `profile_name` | "John" (sender's WhatsApp display name) |
| 3 | Raw phone number | "919876543210" (last resort) |

The `before_insert` hook (Step 2) runs after the document is initialized with the values from `last_message()`, so if a Frappe Contact match is found, it overrides the `profile_name` fallback with the full name.

---

### 4. Backfill Utility for Existing Data

**File:** `whatsapp_chat/api/contacts.py`

**Function:** `resolve_contacts()` (whitelisted)

A utility function to retroactively link existing `WhatsApp Contact` records to their matching Frappe `Contact` records. This is needed because contacts created before this feature was deployed have no `contact` link set.

**What it does:**

1. Fetches all `WhatsApp Contact` records where `contact` is not set.
2. For each, calls `find_contact_by_phone()` with the stored `mobile_no`.
3. If a match is found, updates both the `contact` link and `contact_name`.
4. Returns a summary: `{"updated": <count>, "total": <total_unlinked>}`.

**Usage from bench console:**

```python
import frappe
result = frappe.call("whatsapp_chat.api.contacts.resolve_contacts")
print(result)
# {"updated": 42, "total": 50}
```

**Usage from browser console / API:**

```javascript
frappe.call({
    method: "whatsapp_chat.api.contacts.resolve_contacts",
    callback: function(r) {
        console.log(r.message);
        // {updated: 42, total: 50}
    }
});
```

---

### 5. Automatic Name Sync on Contact Update

**File:** `whatsapp_chat/api/contacts.py`

**Function:** `sync_contact_name(doc, method)`

**File:** `whatsapp_chat/hooks.py`

**Hook:** `Contact.on_update`

When a Frappe `Contact` record is updated (e.g., name change), this hook automatically propagates the new `full_name` to all linked `WhatsApp Contact` records.

```python
# hooks.py
doc_events = {
    "WhatsApp Message": {
        "after_insert": "whatsapp_chat.api.message.last_message"
    },
    "Contact": {
        "on_update": "whatsapp_chat.api.contacts.sync_contact_name"
    }
}
```

**Flow:**

1. User edits a Contact and changes `first_name` from "John" to "Jonathan".
2. Frappe triggers `on_update` on the Contact.
3. `sync_contact_name()` queries all `WhatsApp Contact` records linked to this Contact.
4. Updates `contact_name` on each linked record to the new `full_name`.
5. Chat UI reflects the updated name on next load.

---

## Complete Data Flow

### New Incoming Message (Unknown Number)

```
1. Meta WhatsApp Cloud API sends webhook
       |
2. frappe_whatsapp webhook handler creates WhatsApp Message
       |  (type=Incoming, from=919876543210, profile_name="John")
       |
3. doc_events triggers last_message() in whatsapp_chat
       |
4. No existing WhatsApp Contact found for 919876543210
       |
5. Creates new WhatsApp Contact:
       |  mobile_no = "919876543210"
       |  contact_name = "John"  (from profile_name fallback)
       |
6. before_insert hook fires -> resolve_contact()
       |
7. find_contact_by_phone("919876543210")
       |  Searches tabContact Phone: LIKE '%9876543210'
       |  Searches tabContact.mobile_no: LIKE '%9876543210'
       |
8a. MATCH FOUND (e.g., Contact "John Doe"):
       |  contact = "CONT-00042"
       |  contact_name = "John Doe"  (overrides "John")
       |
8b. NO MATCH:
       |  contact_name stays as "John" (profile_name)
       |  or "919876543210" if no profile_name
       |
9. WhatsApp Contact saved -> after_insert broadcasts to chat UI
       |
10. Chat UI displays "John Doe" (or "John" / "919876543210")
```

### Contact Renamed in Frappe

```
1. User renames Contact "John Doe" -> "Jonathan Doe"
       |
2. Contact.on_update triggers sync_contact_name()
       |
3. Finds WhatsApp Contact linked to this Contact
       |
4. Updates contact_name = "Jonathan Doe"
       |
5. Chat UI shows "Jonathan Doe" on next load
```

---

## Deployment Steps

1. **Deploy the code** to your Frappe bench.

2. **Run migrations** to add the new `contact` column:

   ```bash
   bench --site <your-site> migrate
   ```

3. **Backfill existing contacts** (one-time):

   ```bash
   bench --site <your-site> console
   ```

   ```python
   import frappe
   result = frappe.call("whatsapp_chat.api.contacts.resolve_contacts")
   print(f"Updated {result['updated']} of {result['total']} unlinked contacts")
   frappe.db.commit()
   ```

4. **Verify** by opening the WhatsApp Chat widget -- contacts that matched should now show real names.

---

## Files Modified

| File | Change Summary |
|------|----------------|
| `whatsapp_chat/whatsapp_chat/doctype/whatsapp_contact/whatsapp_contact.json` | Added `contact` Link field to Contact doctype |
| `whatsapp_chat/whatsapp_chat/doctype/whatsapp_contact/whatsapp_contact.py` | Added `_normalize_phone()`, `find_contact_by_phone()`, and `before_insert` hook |
| `whatsapp_chat/api/message.py` | Changed `contact_name` default from `mobile_no` to `doc.profile_name or mobile_no` |
| `whatsapp_chat/api/contacts.py` | Added `resolve_contacts()` backfill utility and `sync_contact_name()` hook |
| `whatsapp_chat/hooks.py` | Added `Contact.on_update` doc_event for name sync |

---

## Edge Cases and Notes

- **Phone number format tolerance:** The last-10-digit matching strategy handles most international formats. Numbers shorter than 10 digits (e.g., some landlines) will match on whatever digits are available.
- **Multiple contacts with same number:** `find_contact_by_phone()` returns the first match (`LIMIT 1`). If multiple Frappe Contacts share the same phone number, the first one found is used.
- **Manual override:** If a user manually sets `contact_name` on a WhatsApp Contact, it will be overridden on the next Contact `on_update`. To prevent this, unset the `contact` Link field.
- **No UI changes required:** The chat widget already displays `contact_name` from the `WhatsApp Contact` record. All changes are at the data layer.
- **WhatsApp Profiles (frappe_whatsapp):** The existing `WhatsApp Profiles` doctype also has a `contact` Link field, but it is independent of this implementation. Both systems can coexist -- `WhatsApp Profiles` is used by the `frappe_whatsapp` app, while `WhatsApp Contact` is used by the `whatsapp_chat` UI.
