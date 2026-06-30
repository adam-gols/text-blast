"""Shared Text Blast logic — Airtable contacts, templates, and macOS Messages sending."""

import json
import os
import re
import subprocess
import sys
import urllib.parse
from datetime import date, datetime

import requests
from dotenv import load_dotenv, set_key

_DATA_DIR = os.path.join(os.path.expanduser("~"), ".sitetools")
os.makedirs(_DATA_DIR, exist_ok=True)

load_dotenv(os.path.join(_DATA_DIR, ".env"))

AIRTABLE_BASE_ID = "appbP3QMzpB7ZaW7W"
STAFFING_TABLE_ID = "tblgMy87FGUjJdd11"
STAFFING_CONTACT_FIELDS = [
    "Channel Title", "Staffing", "Stream Date", "Phone Number (from Staffing)",
]
CONTRACTORS_TABLE = "All GOLS Contractors"
CONTRACTOR_FIELDS = [
    "Employee Display Name", "Full name", "Preferred name", "Phone Number",
    "Pod", "Region", "Stream Details",
]

PREFILL_PATH = os.path.join(_DATA_DIR, "text_blast_prefill.json")
STATE_PATH = os.path.join(_DATA_DIR, "text_blast_state.json")
ERROR_LOG_PATH = os.path.join(_DATA_DIR, "text_blast_errors.log")

_FROZEN = getattr(sys, "frozen", False)


def _kc_get(name, env):
    if not _FROZEN:
        try:
            import keyring
            t = keyring.get_password("SiteTools", name)
            if t:
                return t
        except Exception:
            pass
    return os.getenv(env, "")


def _kc_set(name, env, value):
    if not _FROZEN:
        try:
            import keyring
            keyring.set_password("SiteTools", name, value)
        except Exception:
            pass
    env_path = os.path.join(_DATA_DIR, ".env")
    set_key(env_path, env, value)
    os.environ[env] = value


def get_token():
    return _kc_get("airtable_token", "AIRTABLE_TOKEN")


def _pad_gd(computer: str) -> str:
    m = re.fullmatch(r"GD(\d+)", computer.strip(), re.IGNORECASE)
    if m:
        num = m.group(1)
        if len(num) == 1:
            return f"GD0{num}"
        return f"GD{num}"
    return computer.strip()


def _at_val(v):
    if v is None:
        return ""
    if isinstance(v, list):
        parts = []
        for item in v:
            if isinstance(item, dict):
                parts.append(item.get("name") or item.get("id") or str(item))
            else:
                parts.append(str(item))
        return ", ".join(parts)
    return str(v)


def _esc_formula(s):
    return s.replace("'", "\\'")


def _phone_from_raw(phone_raw):
    if not phone_raw:
        return None
    digits = "".join(c for c in _at_val(phone_raw) if c.isdigit())
    if len(digits) < 7:
        return None
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return f"+{digits}"


def _paginate_airtable(url, headers, params):
    records = []
    try:
        while True:
            r = requests.get(url, headers=headers, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            records.extend(data.get("records", []))
            offset = data.get("offset")
            if not offset:
                break
            params["offset"] = offset
    except Exception:
        return []
    return records


def _date_in_year(stream_date, year=None):
    if not stream_date:
        return False
    if year is None:
        year = date.today().year
    s = str(stream_date).strip()
    if s.startswith(str(year)):
        return True
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            if datetime.strptime(s.split()[0], fmt).year == year:
                return True
        except ValueError:
            continue
    return str(year) in s


def _stream_ids_worked_in_year(headers, record_ids, year=None):
    """Return subset of staffing record IDs with Stream Date in the given year."""
    if not record_ids:
        return set()
    if year is None:
        year = date.today().year
    matched = set()
    id_list = list(record_ids)
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{STAFFING_TABLE_ID}"
    for i in range(0, len(id_list), 40):
        chunk = id_list[i:i + 40]
        formula = "OR(" + ",".join(f"RECORD_ID()='{rid}'" for rid in chunk) + ")"
        params = {
            "filterByFormula": formula,
            "fields[]": ["Stream Date"],
            "cellFormat": "string",
            "timeZone": "America/Los_Angeles",
            "userLocale": "en-us",
        }
        for rec in _paginate_airtable(url, headers, params):
            stream_date = _at_val(rec.get("fields", {}).get("Stream Date", ""))
            if _date_in_year(stream_date, year):
                matched.add(rec["id"])
    return matched


def fetch_pod_names():
    """Return sorted unique Pod values from All GOLS Contractors."""
    token = get_token()
    if not token:
        return []
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(CONTRACTORS_TABLE)}"
    params = {
        "fields[]": ["Pod"],
        "cellFormat": "string",
        "timeZone": "America/Los_Angeles",
        "userLocale": "en-us",
    }
    pods = set()
    for rec in _paginate_airtable(url, headers, params):
        pod = rec.get("fields", {}).get("Pod", "")
        if pod:
            pods.add(pod)
    return sorted(pods)


def fetch_contractor_contacts(pods=None, worked_filter="any", year=None):
    """Fetch contractors filtered by Pod and whether they worked an event this year."""
    token = get_token()
    if not token:
        return []
    if year is None:
        year = date.today().year

    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{urllib.parse.quote(CONTRACTORS_TABLE)}"

    conditions = []
    if pods:
        pod_conditions = [f"{{Pod}}='{_esc_formula(p)}'" for p in pods]
        conditions.append(
            f"OR({','.join(pod_conditions)})" if len(pod_conditions) > 1 else pod_conditions[0]
        )
    formula = f"AND({','.join(conditions)})" if conditions else None

    params = {
        "fields[]": CONTRACTOR_FIELDS,
    }
    if formula:
        params["filterByFormula"] = formula

    records = _paginate_airtable(url, headers, params)

    if worked_filter != "any":
        all_stream_ids = set()
        for rec in records:
            all_stream_ids.update(rec.get("fields", {}).get("Stream Details") or [])
        worked_ids = _stream_ids_worked_in_year(headers, all_stream_ids, year)
        filtered = []
        for rec in records:
            stream_ids = set(rec.get("fields", {}).get("Stream Details") or [])
            worked = bool(stream_ids & worked_ids)
            if worked_filter == "yes" and worked:
                filtered.append(rec)
            elif worked_filter == "no" and not worked:
                filtered.append(rec)
        records = filtered

    seen_phones = set()
    contacts = []
    for rec in records:
        f = rec.get("fields", {})
        phone = _phone_from_raw(f.get("Phone Number", ""))
        if not phone or phone in seen_phones:
            continue
        seen_phones.add(phone)
        name = (
            _at_val(f.get("Employee Display Name", ""))
            or _at_val(f.get("Preferred name", ""))
            or _at_val(f.get("Full name", ""))
        )
        contacts.append({
            "name": name,
            "phone": phone,
            "pod": _at_val(f.get("Pod", "")),
            "region": _at_val(f.get("Region", "")),
            "site": "",
            "computer": "",
            "channel": "",
            "date": "",
        })
    contacts.sort(key=lambda c: c["name"])
    return contacts


def fetch_staff_contacts(min_date=None, max_date=None, event_name=None):
    """Fetch staff contacts from Airtable.
    Returns list of dicts with name, phone, site, computer, channel, date."""
    token = get_token()
    if not token:
        return []
    headers = {"Authorization": f"Bearer {token}"}

    conditions = []
    if event_name:
        esc_name = event_name.replace("'", "\\'")
        conditions.append(f"FIND('{esc_name}', {{Event Name}}) > 0")
    if min_date and max_date:
        conditions.append(f"NOT(IS_BEFORE({{Stream Date}}, '{min_date}'))")
        conditions.append(f"NOT(IS_AFTER({{Stream Date}}, '{max_date}'))")
    if conditions:
        formula = f"AND({','.join(conditions)})" if len(conditions) > 1 else conditions[0]
    else:
        formula = "NOT({Stream Date} = '')"

    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{STAFFING_TABLE_ID}"
    params = {
        "filterByFormula": formula,
        "fields[]": STAFFING_CONTACT_FIELDS,
        "cellFormat": "string",
        "timeZone": "America/Los_Angeles",
        "userLocale": "en-us",
    }
    records = []
    try:
        while True:
            r = requests.get(url, headers=headers, params=params, timeout=20)
            data = r.json()
            records.extend(data.get("records", []))
            offset = data.get("offset")
            if not offset:
                break
            params["offset"] = offset
    except Exception:
        return []

    seen_phones = set()
    contacts = []
    for rec in records:
        f = rec.get("fields", {})
        phone = _phone_from_raw(f.get("Phone Number (from Staffing)", ""))
        if not phone:
            continue

        if phone in seen_phones:
            continue
        seen_phones.add(phone)

        title = f.get("Channel Title", "")
        parts = [p.strip() for p in title.split("|")]
        contacts.append({
            "name": _at_val(f.get("Staffing", "")),
            "phone": phone,
            "channel": parts[0] if len(parts) > 0 else "",
            "computer": _pad_gd(parts[1]) if len(parts) > 1 else "",
            "date": _at_val(f.get("Stream Date", "")),
            "site": parts[3] if len(parts) > 3 else "",
        })
    contacts.sort(key=lambda c: c["name"])
    return contacts


def fetch_event_names():
    """Return sorted unique event names from the staffing table."""
    token = get_token()
    if not token:
        return []
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{STAFFING_TABLE_ID}"
    params = {
        "fields[]": ["Event Name"],
        "cellFormat": "string",
        "timeZone": "America/Los_Angeles",
        "userLocale": "en-us",
    }
    events = set()
    try:
        while True:
            r = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=20,
            )
            data = r.json()
            for rec in data.get("records", []):
                name = rec.get("fields", {}).get("Event Name", "")
                if name:
                    events.add(name)
            offset = data.get("offset")
            if not offset:
                break
            params["offset"] = offset
    except Exception:
        return []
    return sorted(events, reverse=True)


def normalize_phone(raw):
    """Normalize a phone string to E.164, or return None if invalid."""
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if len(digits) >= 7:
        return f"+{digits}"
    return None


def parse_contacts(raw):
    """Parse contacts from text. Returns list of (name, phone) tuples."""
    seen_phones = set()
    contacts = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("---"):
            continue
        if "\t" in line:
            parts = [p.strip() for p in line.split("\t") if p.strip()]
        elif "," in line:
            parts = [p.strip() for p in line.split(",") if p.strip()]
        else:
            parts = [line.strip()]

        name, phone = "", ""
        for part in parts:
            digits = "".join(c for c in part if c.isdigit())
            if len(digits) >= 7:
                phone = part
            elif part and not name:
                name = part

        if not phone:
            continue
        normalized = normalize_phone(phone)
        if not normalized or normalized in seen_phones:
            continue
        seen_phones.add(normalized)
        contacts.append((name.strip(), normalized))
    return contacts


def _first_name(name):
    """First word of a display name, for {name} in templates."""
    if not name or not str(name).strip():
        return "there"
    return str(name).strip().split()[0]


def apply_template(template, enriched):
    msg = template
    first = _first_name(enriched.get("name"))
    msg = msg.replace("{first name}", first)
    msg = msg.replace("{name}", first)
    msg = msg.replace("{site}", enriched.get("site") or "")
    msg = msg.replace("{computer}", enriched.get("computer") or "")
    msg = msg.replace("{channel}", enriched.get("channel") or "")
    msg = msg.replace("{date}", enriched.get("date") or "")
    msg = msg.replace("{pod}", enriched.get("pod") or "")
    msg = msg.replace("{region}", enriched.get("region") or "")
    return msg


def get_enriched(name, phone, enriched_contacts):
    for c in enriched_contacts:
        if c.get("phone") == phone:
            return c
    return {
        "name": name or "there",
        "phone": phone,
        "site": "",
        "computer": "",
        "channel": "",
        "date": "",
        "pod": "",
        "region": "",
    }


def format_phone_for_messages(phone):
    """Format E.164 phone for macOS Messages AppleScript (US display format)."""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return phone


def _normalize_message(msg):
    """Normalize line endings without changing message layout."""
    return msg.replace("\r\n", "\n").replace("\r", "\n")


def _applescript_message_expr(msg):
    """Build an AppleScript expression for a (possibly multi-line) message."""
    msg = _normalize_message(msg)
    msg = msg.replace("\\", "\\\\").replace('"', '\\"')
    parts = msg.split("\n")
    if len(parts) == 1:
        return f'"{parts[0]}"'
    return " & return & ".join(f'"{part}"' for part in parts)


def _parse_applescript_error(result, output):
    """Turn osascript output/stderr into a short user-facing message."""
    if output.startswith("error:"):
        return output[6:]
    stderr = (result.stderr or "").strip()
    if not stderr and not output:
        return "Messages did not confirm delivery"
    combined = "\n".join(filter(None, [stderr, output]))
    if "-1743" in combined or "not authorized" in combined.lower():
        return (
            "Automation not allowed — open System Settings → Privacy & Security → "
            "Automation and allow Messages for Python / Terminal / Text Blast"
        )
    if "-25211" in combined or "assistive access" in combined.lower():
        return (
            "Accessibility not allowed — open System Settings → Privacy & Security → "
            "Accessibility and allow Python / Terminal / Text Blast"
        )
    if "not allowed to send keystrokes" in combined.lower():
        return (
            "Accessibility not allowed — open System Settings → Privacy & Security → "
            "Accessibility and allow Terminal / Python (required for group texts)"
        )
    for line in reversed(combined.splitlines()):
        line = line.strip()
        if "execution error:" in line:
            msg = line.split("execution error:", 1)[-1].strip()
            if msg.endswith(")"):
                msg = msg.rsplit("(", 1)[0].strip()
            return msg or line
        if "syntax error:" in line:
            return line
    return combined.splitlines()[-1] if combined else "Unknown AppleScript error"


def _run_applescript(script, timeout=30):
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = (result.stdout or "").strip()
    if output == "ok":
        return True, ""
    if output.startswith("error:"):
        return False, output[6:]
    if result.returncode != 0 or not output:
        return False, _parse_applescript_error(result, output)
    return False, output


def _build_send_script(phone_display, msg):
    """Single-recipient send script using iMessage then SMS fallback."""
    msg_expr = _applescript_message_expr(msg)
    phone_esc = phone_display.replace('"', '\\"')
    return (
        f'try\n'
        f'  tell application "Messages"\n'
        f'    set targetBuddy to "{phone_esc}"\n'
        f'    set targetService to id of 1st account whose service type = iMessage\n'
        f'    set theBuddy to participant targetBuddy of account id targetService\n'
        f'    send {msg_expr} to theBuddy\n'
        f'  end tell\n'
        f'  return "ok"\n'
        f'on error errMsg number errNum\n'
        f'  try\n'
        f'    tell application "Messages"\n'
        f'      set targetBuddy to "{phone_esc}"\n'
        f'      set targetService to id of 1st account whose service type = SMS\n'
        f'      set theBuddy to participant targetBuddy of account id targetService\n'
        f'      send {msg_expr} to theBuddy\n'
        f'    end tell\n'
        f'    return "ok"\n'
        f'  on error errMsg2 number errNum2\n'
        f'    return "error:" & errNum2 & ":" & errMsg2\n'
        f'  end try\n'
        f'end try'
    )


def _phone_digits10(phone):
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return digits


def _build_find_group_chat_script(phone, cc_phone, msg):
    """Send only to an existing 2-person group (contact + CC, nobody else)."""
    d1 = _phone_digits10(phone)
    d2 = _phone_digits10(cc_phone)
    msg_expr = _applescript_message_expr(msg)
    return (
        f'try\n'
        f'  tell application "Messages"\n'
        f'    set wantA to "{d1}"\n'
        f'    set wantB to "{d2}"\n'
        f'    repeat with c in chats\n'
        f'      set foundA to false\n'
        f'      set foundB to false\n'
        f'      set phoneParticipants to 0\n'
        f'      repeat with p in participants of c\n'
        f'        set pid to id of p as text\n'
        f'        if pid contains "+" then\n'
        f'          set phoneParticipants to phoneParticipants + 1\n'
        f'          if pid contains wantA then set foundA to true\n'
        f'          if pid contains wantB then set foundB to true\n'
        f'        end if\n'
        f'      end repeat\n'
        f'      if foundA and foundB and phoneParticipants is 2 then\n'
        f'        send {msg_expr} to c\n'
        f'        return "ok"\n'
        f'      end if\n'
        f'    end repeat\n'
        f'    return "error:not_found:no existing group chat"\n'
        f'  end tell\n'
        f'on error errMsg number errNum\n'
        f'  return "error:" & errNum & ":" & errMsg\n'
        f'end try'
    )


def _build_compose_group_script(phone1, phone2, msg):
    """Create a new group via Messages UI (works when AppleScript create is broken)."""
    msg_expr = _applescript_message_expr(msg)
    p1 = phone1.replace('"', '\\"')
    p2 = phone2.replace('"', '\\"')
    return (
        f'try\n'
        f'  set msgText to {msg_expr}\n'
        f'  set the clipboard to msgText\n'
        f'  tell application "Messages" to activate\n'
        f'  delay 0.5\n'
        f'  tell application "System Events"\n'
        f'    tell process "Messages"\n'
        f'      keystroke "n" using command down\n'
        f'      delay 0.7\n'
        f'      keystroke "{p1}"\n'
        f'      delay 0.4\n'
        f'      key code 36\n'
        f'      delay 0.35\n'
        f'      keystroke "{p2}"\n'
        f'      delay 0.4\n'
        f'      key code 36\n'
        f'      delay 0.35\n'
        f'      keystroke tab\n'
        f'      delay 0.25\n'
        f'      keystroke "v" using command down\n'
        f'      delay 0.25\n'
        f'      key code 36\n'
        f'    end tell\n'
        f'  end tell\n'
        f'  return "ok"\n'
        f'on error errMsg number errNum\n'
        f'  return "error:" & errNum & ":" & errMsg\n'
        f'end try'
    )


def _build_group_send_script(phone1, phone2, msg):
    """Two-recipient group send using iMessage then SMS fallback."""
    msg_expr = _applescript_message_expr(msg)
    p1 = phone1.replace('"', '\\"')
    p2 = phone2.replace('"', '\\"')
    return (
        f'try\n'
        f'  tell application "Messages"\n'
        f'    set targetService to 1st service whose service type = iMessage\n'
        f'    set b1 to buddy "{p1}" of targetService\n'
        f'    set b2 to buddy "{p2}" of targetService\n'
        f'    set theChat to make new text chat with properties {{participants:{{b1, b2}}}}\n'
        f'    send {msg_expr} to theChat\n'
        f'  end tell\n'
        f'  return "ok"\n'
        f'on error errMsg number errNum\n'
        f'  try\n'
        f'    tell application "Messages"\n'
        f'      set targetService to 1st service whose service type = SMS\n'
        f'      set b1 to buddy "{p1}" of targetService\n'
        f'      set b2 to buddy "{p2}" of targetService\n'
        f'      set theChat to make new text chat with properties {{participants:{{b1, b2}}}}\n'
        f'      send {msg_expr} to theChat\n'
        f'    end tell\n'
        f'    return "ok"\n'
        f'  on error errMsg2 number errNum2\n'
        f'    return "error:" & errNum2 & ":" & errMsg2\n'
        f'  end try\n'
        f'end try'
    )


def _phone_formats(phone):
    """Candidate phone formats to try with Messages."""
    digits = "".join(c for c in phone if c.isdigit())
    formats = []
    if len(digits) == 11 and digits.startswith("1"):
        d10 = digits[1:]
        formats.append(f"({d10[:3]}) {d10[3:6]}-{d10[6:]}")
        formats.append(d10)
        formats.append(f"+{digits}")
        formats.append(digits)
    elif len(digits) == 10:
        formats.append(f"({digits[:3]}) {digits[3:6]}-{digits[6:]}")
        formats.append(digits)
        formats.append(f"+1{digits}")
    else:
        formats.append(phone)
    seen = set()
    out = []
    for f in formats:
        if f and f not in seen:
            seen.add(f)
            out.append(f)
    return out


def _send_to_one_phone(phone, msg):
    """Try sending to one phone using several display formats."""
    last_err = "Could not send message"
    for fmt in _phone_formats(phone):
        ok, err = _run_applescript(_build_send_script(fmt, msg))
        if ok:
            return True, ""
        last_err = err or last_err
    return False, last_err


def _send_group_message(phone, cc_phone, msg):
    """Try group text; fall back to separate copies if macOS blocks group creation."""
    last_err = "Could not send group message"

    ok, err = _run_applescript(
        _build_find_group_chat_script(phone, cc_phone, msg), timeout=90)
    if ok:
        return True, ""
    last_err = err or last_err

    for pf in _phone_formats(phone)[:2]:
        for cf in _phone_formats(cc_phone)[:2]:
            ok, err = _run_applescript(
                _build_compose_group_script(pf, cf, msg), timeout=60)
            if ok:
                return True, ""
            last_err = err or last_err

    ok1, err1 = _send_to_one_phone(phone, msg)
    if not ok1:
        return False, f"Group unavailable ({last_err}); direct send failed: {err1}"
    ok2, err2 = _send_to_one_phone(cc_phone, msg)
    if not ok2:
        return False, f"Sent to contact; CC copy failed: {err2}"
    return True, "separate_copy"


def send_text_message(phone, msg, cc_phone=None):
    """Send one text via macOS Messages. Returns (success, error_message)."""
    if sys.platform != "darwin":
        return False, "macOS only"

    msg = _normalize_message(msg)
    phone = phone.replace('"', "")

    if cc_phone:
        cc = cc_phone.replace('"', "")
        if cc != phone:
            return _send_group_message(phone, cc, msg)

    return _send_to_one_phone(phone, msg)


def notify(title, message):
    try:
        safe_msg = message.replace('"', "'")
        safe_title = title.replace('"', "'")
        if sys.platform == "darwin":
            os.system(
                f"""osascript -e 'display notification "{safe_msg}" """
                f"""with title "{safe_title}" sound name "Glass"' """
            )
    except Exception:
        pass


def write_prefill(path, contacts_text, template, enriched_contacts):
    data = {
        "contacts_text": contacts_text,
        "template": template,
        "enriched_contacts": enriched_contacts,
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def read_prefill(path):
    with open(path) as f:
        return json.load(f)


def read_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def write_state(data):
    with open(STATE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def log_send_errors(entries):
    """Append send failure entries to the error log file."""
    if not entries:
        return ERROR_LOG_PATH
    import datetime as _dt
    try:
        with open(ERROR_LOG_PATH, "a") as f:
            f.write(f"\n--- {_dt.datetime.now().isoformat()} ---\n")
            for e in entries:
                f.write(f"{e.get('name', '')}\t{e.get('phone', '')}\t{e.get('error', '')}\n")
        return ERROR_LOG_PATH
    except Exception:
        return ""
