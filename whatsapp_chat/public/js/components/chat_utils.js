import moment from 'moment';

function get_time(time) {
  let current_time;
  if (time) {
    current_time = moment(time);
  } else {
    current_time = moment();
  }
  return current_time.format('h:mm A');
}

function get_date_from_now(dateObj, type) {
  const sameDay = type === 'space' ? '[Today]' : 'h:mm A';
  const elseDay = type === 'space' ? 'MMM D, YYYY' : 'DD/MM/YYYY';
  const result = moment(dateObj).calendar(null, {
    sameDay: sameDay,
    lastDay: '[Yesterday]',
    lastWeek: elseDay,
    sameElse: elseDay,
  });
  return result;
}

function is_date_change(dateObj, prevObj) {
  const curDate = moment(dateObj).format('DD/MM/YYYY');
  const prevDate = moment(prevObj).format('DD/MM/YYYY');
  return curDate !== prevDate;
}

function scroll_to_bottom($element) {
  $element.animate(
    {
      scrollTop: $element[0].scrollHeight,
    },
    300
  );
}

function is_image(filename) {
  const allowedExtensions = /(\.jpg|\.jpeg|\.png|\.gif|\.webp)$/i;
  if (!allowedExtensions.exec(filename)) {
    return false;
  }
  return true;
}

async function get_rooms(email) {
  const res = await frappe.call({
    type: 'GET',
    method: 'whatsapp_chat.api.contacts.get',
    args: {
      email: email,
    },
  });
  return await res.message;
}

async function get_messages(room, user_no) {
  const res = await frappe.call({
    method: 'whatsapp_chat.api.message.get_all',
    args: {
      room: room,
      user_no: user_no,
    },
  });
  return await res.message;
}

async function send_message(content, user, room, user_no, attachment) {
  try {
    await frappe.call({
      method: 'whatsapp_chat.api.message.send',
      args: {
        content: content,
        user: user,
        room: room,
        user_no: user_no,
        attachment: attachment
      },
    });
  } catch (error) {
    frappe.msgprint({
      title: __('Error'),
      message: __('Something went wrong. Please refresh and try again.'),
    });
  }
}

async function get_settings(token) {
  const res = await frappe.call({
    type: 'GET',
    method: 'whatsapp_chat.api.config.settings',
    args: {
      token: token,
    },
  });
  return await res.message;
}

async function mark_message_read(room) {
  try {
    await frappe.call({
      method: 'whatsapp_chat.api.message.mark_as_read',
      args: {
        room: room,
      },
    });
  } catch (error) {
    //pass
  }
}


async function create_guest({ email, full_name, message }) {
  const res = await frappe.call({
    method: 'chat.api.user.get_guest_room',
    args: {
      email: email,
      full_name: full_name,
      message: message,
    },
  });
  return await res.message;
}

async function set_typing(room, user, is_typing, is_guest) {
  try {
    await frappe.call({
      method: 'whatsapp_chat.api.message.set_typing',
      args: {
        room: room,
        user: user,
        is_typing: is_typing,
        is_guest: is_guest,
      },
    });
  } catch (error) {
    //pass
  }
}

async function create_private_room(contact_name, mobile_no, email) {
  await frappe.call({
    method: 'whatsapp_chat.api.contacts.create',
    args: {
      contact_name: contact_name,
      mobile_no: mobile_no,
      email: email
    },
  });
}

async function set_user_settings(settings) {
  await frappe.call({
    method: 'chat.api.config.user_settings',
    args: {
      settings: settings,
    },
  });
}

function get_avatar_html(room_type, user_email, room_name) {
  let avatar_html;
  if (room_type === 'Direct' && 'desk' in frappe) {
    avatar_html = frappe.avatar(user_email, 'avatar-medium');
  } else {
    avatar_html = frappe.get_avatar('avatar-medium', room_name);
  }
  return avatar_html;
}

function set_notification_count(type) {
  const current_count = frappe.Chat.settings.unread_count;
  if (type === 'increment') {
    $('#chat-notification-count').text(current_count + 1);
    frappe.Chat.settings.unread_count += 1;
  } else {
    if (current_count - 1 === 0) {
      $('#chat-notification-count').text('');
    } else {
      $('#chat-notification-count').text(current_count - 1);
    }
    frappe.Chat.settings.unread_count -= 1;
  }
}

function format_whatsapp_template(content) {
  if (typeof content !== 'string') return null;
  // Basic heuristic: Is it a stringified dict containing a python dict template?
  if (!content.trim().startsWith('{') || !content.includes('components')) {
    return null;
  }

  try {
    // Attempt to convert python dict to valid JSON (single quotes to double quotes)
    // This regex carefully avoids replacing single quotes inside actual word contents like "don't" (if escaped)
    // but the python dict output usually surrounds keys/values with strictly single quotes unless there's a nested single quote.
    const jsonStr = content.replace(/'((?:\\'|[^'])*)'/g, '"$1"');
    const obj = JSON.parse(jsonStr);

    if (obj && obj.components && Array.isArray(obj.components)) {
      let html = `<div class="whatsapp-template-card">`;
      // We can display the template name at the top as a faint label
      html += `<div class="whatsapp-template-header text-muted" style="font-size: 0.75rem; border-bottom: 1px solid var(--border-color); padding-bottom: 4px; margin-bottom: 8px;">
        <i class="fa fa-file-text-o"></i> ${obj.name || 'Template'}
      </div>`;

      // Iterate through components
      obj.components.forEach(component => {
        if (component.type === 'header' && component.parameters) {
          component.parameters.forEach(param => {
            if (param.type === 'document' && param.document) {
              html += `<div class="whatsapp-template-document" style="margin-bottom: 8px;">
                  <a href="${param.document.link}" target="_blank" class="btn btn-xs btn-default">
                    <i class="fa fa-download"></i> ${param.document.filename || 'Download Document'}
                  </a>
                </div>`;
            } else if (param.type === 'image' && param.image) {
              html += `<div class="whatsapp-template-image" style="margin-bottom: 8px;">
                  <img src="${param.image.link}" style="max-width: 100%; border-radius: var(--border-radius);" />
                </div>`;
            } else if (param.type === 'text' && param.text) {
              html += `<div class="whatsapp-template-text-header" style="font-weight: bold; margin-bottom: 4px;">${param.text}</div>`;
            }
          });
        }
        else if (component.type === 'body' && component.parameters) {
          html += `<div class="whatsapp-template-body" style="background: var(--gray-100); padding: 8px; border-radius: var(--border-radius); font-size: 0.85rem; color: var(--text-color);">`;
          component.parameters.forEach(param => {
            if (param.type === 'text') {
              html += `<div class="whatsapp-template-param"><span class="text-muted">•</span> <b>${param.text}</b></div>`;
            }
          });
          html += `</div>`;
        }
      });
      html += `</div>`;
      return html;
    }
  } catch (e) {
    // If parsing fails for any reason (e.g. unescaped character), fail silently and fall back to raw text.
    return null;
  }
  return null;
}

export {
  get_time,
  scroll_to_bottom,
  get_rooms,
  get_messages,
  get_settings,
  create_guest,
  send_message,
  get_date_from_now,
  is_date_change,
  mark_message_read,
  set_typing,
  is_image,
  create_private_room,
  set_user_settings,
  get_avatar_html,
  set_notification_count,
  format_whatsapp_template,
};
