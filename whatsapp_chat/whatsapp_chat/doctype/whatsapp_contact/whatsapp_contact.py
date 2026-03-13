# Copyright (c) 2024, shridhar patil and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class WhatsAppContact(Document):

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
