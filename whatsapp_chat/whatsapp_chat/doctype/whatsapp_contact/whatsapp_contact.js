// Copyright (c) 2024, shridhar patil and contributors
// For license information, please see license.txt

frappe.ui.form.on("WhatsApp Contact", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.mobile_no) {
			frm.add_custom_button(__("Start Chat"), function () {
				// Open the chat widget
				let $chat_icon = $(".chat-navbar-icon");
				if ($chat_icon.length && !$(".chat-element").is(":visible")) {
					$chat_icon.click();
				}

				// Wait for widget to render, then open the specific room
				setTimeout(() => {
					let chat_rooms = frappe.Chat?.chat_list?.chat_rooms || [];
					let room = chat_rooms.find(
						(r) => r[0] === frm.doc.name
					);
					if (room) {
						room[1].$chat_room.click();
					} else {
						frappe.show_alert({
							message: __("Chat room will appear when you send the first message."),
							indicator: "blue",
						});
					}
				}, 300);
			}, __("WhatsApp"));

			frm.add_custom_button(__("Send Message"), function () {
				let d = new frappe.ui.Dialog({
					title: __("Send WhatsApp Message"),
					fields: [
						{
							label: __("To"),
							fieldname: "to",
							fieldtype: "Data",
							default: frm.doc.mobile_no,
							read_only: 1,
						},
						{
							label: __("Message"),
							fieldname: "message",
							fieldtype: "Small Text",
							reqd: 1,
						},
					],
					primary_action_label: __("Send"),
					primary_action(values) {
						frappe.call({
							method: "whatsapp_chat.api.message.send",
							args: {
								content: values.message,
								user: frappe.session.user,
								room: frm.doc.name,
								user_no: frm.doc.mobile_no,
							},
							callback() {
								frappe.show_alert({
									message: __("Message sent"),
									indicator: "green",
								});
								d.hide();
							},
						});
					},
				});
				d.show();
			}, __("WhatsApp"));
		}
	},

	contact(frm) {
		if (!frm.doc.contact) {
			frm.set_value("contact_name", "");
			frm.set_value("mobile_no", "");
			return;
		}

		frappe.db.get_value("Contact", frm.doc.contact,
			["full_name", "mobile_no", "phone"],
			(r) => {
				if (!r) return;

				if (r.full_name) {
					frm.set_value("contact_name", r.full_name);
				}

				// Use mobile_no first, fall back to phone
				let number = r.mobile_no || r.phone;
				if (number) {
					frm.set_value("mobile_no", number);
				} else {
					// Check phone_nos child table as last resort
					frappe.call({
						method: "frappe.client.get_list",
						args: {
							doctype: "Contact Phone",
							filters: { parent: frm.doc.contact },
							fields: ["phone"],
							limit_page_length: 1,
						},
						callback(resp) {
							if (resp.message && resp.message.length > 0) {
								frm.set_value("mobile_no", resp.message[0].phone);
							}
						},
					});
				}
			}
		);
	},
});
