import os
import requests
from datetime import datetime, timezone
import pytz
from dotenv import load_dotenv

# === Load config from config.env ===
load_dotenv("config.env")

# === Environment Variables ===
HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY")
DIALPAD_API_KEY = os.getenv("DIALPAD_COOLBEANS_API_KEY")
DIALPAD_COMPANY_ID = os.getenv("DIALPAD_COMPANY_ID")
SYNC_SCHEDULE = os.getenv("SYNC_SCHEDULE", "Manual (Run Now)")

SEARCH_URL = "https://api.hubapi.com/crm/v3/objects/contacts/search"
DIALPAD_CONTACTS_URL = "https://dialpad.com/api/v2/contacts"

def should_run_today():
    """Check if the script should run today based on SYNC_SCHEDULE."""
    aest = pytz.timezone("Australia/Sydney")
    today = datetime.now(aest)

    if SYNC_SCHEDULE == "Daily":
        return True
    elif SYNC_SCHEDULE == "Weekly":
        return today.weekday() == 0  # Monday
    elif SYNC_SCHEDULE == "Monthly":
        return today.day == 1
    elif SYNC_SCHEDULE == "Manual (Run Now)":
        return True
    return False

def fetch_today_contacts():
    HEADERS = {
        "Authorization": f"Bearer {HUBSPOT_API_KEY}",
        "Content-Type": "application/json"
    }

    aest = pytz.timezone('Australia/Sydney')
    now_aest = datetime.now(aest)
    start_of_day_aest = now_aest.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_utc = start_of_day_aest.astimezone(timezone.utc)
    start_of_day_iso = start_of_day_utc.isoformat()

    payload = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "createdate",
                        "operator": "GTE",
                        "value": start_of_day_iso
                    }
                ]
            }
        ],
        "properties": ["firstname", "lastname", "email", "phone", "hs_lead_status"],
        "limit": 100
    }

    contacts = []
    after = None
    has_more = True

    while has_more:
        if after:
            payload["after"] = after
        res = requests.post(SEARCH_URL, headers=HEADERS, json=payload)
        res.raise_for_status()
        data = res.json()
        contacts.extend(data.get("results", []))
        after = data.get("paging", {}).get("next", {}).get("after")
        has_more = bool(after)

    return contacts

def fetch_all_shared_dialpad_contacts():
    headers = {
        "Authorization": f"Bearer {DIALPAD_API_KEY}",
        "Content-Type": "application/json"
    }
    contacts = []
    params = {"limit": 100}
    has_more = True
    after = None

    while has_more:
        if after:
            params["cursor"] = after
        else:
            params.pop("cursor", None)

        res = requests.get(DIALPAD_CONTACTS_URL, headers=headers, params=params)
        res.raise_for_status()
        data = res.json()

        page_contacts = [c for c in data.get("items", []) if c.get("type") == "shared"]
        contacts.extend(page_contacts)

        after = data.get("cursor")
        has_more = bool(after)

    return contacts

def build_dialpad_lookup(contacts):
    email_to_contact = {}
    phone_to_contact = {}

    for c in contacts:
        contact_id = c.get("id")
        emails = c.get("emails") or []
        phones = c.get("phones") or []

        for email in emails:
            email_to_contact[email.lower()] = c
        for phone in phones:
            phone_to_contact[phone] = c

    return email_to_contact, phone_to_contact

def update_dialpad_contact(contact_id, payload):
    url = f"{DIALPAD_CONTACTS_URL}/{contact_id}"
    headers = {
        "Authorization": f"Bearer {DIALPAD_API_KEY}",
        "Content-Type": "application/json"
    }
    res = requests.patch(url, headers=headers, json=payload)
    return res

def delete_from_dialpad(contact_id):
    url = f"{DIALPAD_CONTACTS_URL}/{contact_id}"
    headers = {
        "Authorization": f"Bearer {DIALPAD_API_KEY}",
        "Content-Type": "application/json"
    }
    res = requests.delete(url, headers=headers)
    return res

def push_to_dialpad(contacts, email_lookup, phone_lookup):
    headers = {
        "Authorization": f"Bearer {DIALPAD_API_KEY}",
        "Content-Type": "application/json"
    }

    for c in contacts:
        props = c.get("properties", {})
        first_name = props.get("firstname", "")
        last_name = props.get("lastname", "")
        email = props.get("email", "").lower()
        phone = props.get("phone", "")
        lead_status = props.get("hs_lead_status", "").strip().lower()

        if not email and not phone:
            continue

        existing_contact = email_lookup.get(email) if email else None

        if lead_status == "unqualified" and existing_contact:
            contact_id = existing_contact.get("id")
            res = delete_from_dialpad(contact_id)
            if res.status_code == 200:
                print(f"
