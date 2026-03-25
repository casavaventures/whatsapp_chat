# Copyright (c) 2024, shridhar patil and contributors
# For license information, please see license.txt

import re

import frappe
from frappe.model.document import Document


def _normalize_phone(number):
	"""Strip non-digit characters and return last 10 digits for comparison."""
	digits = re.sub(r"\D", "", number or "")
	return digits[-10:] if len(digits) >= 10 else digits


def find_contact_by_phone(mobile_no):
	"""Find a Frappe Contact by matching phone number (last 10 digits).

	Searches both the Contact Phone child table and the Contact's mobile_no field.
	Returns (contact_name, full_name) or (None, None).
	"""
	suffix = _normalize_phone(mobile_no)
	if not suffix:
		return None, None

	like_pattern = f"%{suffix}"

	# Search Contact Phone child table
	result = frappe.db.sql(
		"""
		SELECT cp.parent, c.name, COALESCE(NULLIF(c.full_name, ''), c.first_name) as full_name
		FROM `tabContact Phone` cp
		JOIN `tabContact` c ON c.name = cp.parent
		WHERE REPLACE(REPLACE(cp.phone, '+', ''), ' ', '') LIKE %s
		LIMIT 1
		""",
		(like_pattern,),
		as_dict=True,
	)

	if result:
		return result[0].name, result[0].full_name

	# Fallback: search Contact.mobile_no directly
	result = frappe.db.sql(
		"""
		SELECT name, COALESCE(NULLIF(full_name, ''), first_name) as full_name
		FROM `tabContact`
		WHERE REPLACE(REPLACE(mobile_no, '+', ''), ' ', '') LIKE %s
		LIMIT 1
		""",
		(like_pattern,),
		as_dict=True,
	)

	if result:
		return result[0].name, result[0].full_name

	return None, None


class WhatsAppContact(Document):

	def autoname(self):
		mobile = self.mobile_no or ""
		name = self.contact_name or ""
		if mobile and name and name != mobile:
			self.name = f"{mobile} - {name}"
		elif mobile:
			self.name = mobile
		elif name:
			self.name = name

	def before_insert(self):
		self.resolve_contact()

	def resolve_contact(self):
		"""Try to link this WhatsApp Contact to a Frappe Contact by phone number."""
		if self.contact:
			return

		contact_name, full_name = find_contact_by_phone(self.mobile_no)
		if contact_name:
			self.contact = contact_name
			if full_name:
				self.contact_name = full_name

	def after_insert(self):
		users = frappe.get_all('User', filters={'enabled': 1, 'user_type': 'System User'}, fields=['name'])
		for user in users:
			if frappe.has_permission('WhatsApp Contact', ptype='read', user=user.name):
				frappe.publish_realtime(
					"new_room_creation", 
					{
						"user": user.name,  
						"room_name": self.contact_name,
						"room": self.name,
						"type": "Direct"
					}, 
					user=user.name
				)
