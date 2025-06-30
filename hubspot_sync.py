import os
import requests
from datetime import datetime, timezone
import pytz
from dotenv import load_dotenv

# === Load config from config.env ===
load_dotenv("config.env")

# Print current config state
print("🛠️ Delete feature enabled:", os.getenv("DELETE_UNQUALIFIED_CONTACTS"))

# === Environment Variables ===
HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY")
DIALPAD_API_KEY = os.getenv("DIALPAD_COOLBEANS_API_KEY")
DIALPAD_COMPANY_ID = os.getenv("DIALPAD_COMPANY_ID")
SYNC_SCHEDULE = os.getenv("SYNC_SCHEDULE", "Manual (Run Now)")
DELETE_UNQUALIFIED = os.getenv("DELETE_UNQUALIFIED", "false").lower() == "true"

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

    # Fetch contacts created today (same as before)
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
        # Include Lead Status property for deletion logic
        "properties": ["firstname", "lastname", "email", "phone", "lead_status"],
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

def delete_dialpad_contact(contact_id):
    url = f"{DIALPAD_CONTACTS_URL}/{contact_id}"
    headers = {
        "Authorization": f"Bearer {DIALPAD_API_KEY}",
    }
    res = requests.delete(url, headers=headers)
    return res

def push_to_dialpad(contacts, email_lookup, phone_lookup):
    headers = {
        "Authorization": f"Bearer {DIALPAD_API_KEY}",
        "Content-Type": "application/json"
    }

    added_count = 0
    deleted_count = 0

    for c in contacts:
        props = c.get("properties", {})
        first_name = props.get("firstname", "")
        last_name = props.get("lastname", "")
        email = props.get("email", "").lower()
        phone = props.get("phone", "")
        lead_status = props.get("lead_status", "").lower()

        if DELETE_UNQUALIFIED and lead_status == "unqualified":
            # If unqualified and contact exists in Dialpad, delete it
            existing_contact = email_lookup.get(email) if email else None
            if existing_contact:
                contact_id = existing_contact.get("id")
                res = delete_dialpad_contact(contact_id)
                if res.status_code == 204:
                    print(f"🗑️ Deleted unqualified contact: {first_name} {last_name}")
                    deleted_count += 1
                else:
                    print(f"❌ Failed to delete {first_name} {last_name}: {res.status_code} {res.text}")
            else:
                print(f"ℹ️ Unqualified contact not found in Dialpad: {first_name} {last_name}")
            # Skip further processing for unqualified
            continue

        if not email and not phone:
            continue

        existing_contact = email_lookup.get(email) if email else None

        if existing_contact:
            dialpad_phones = existing_contact.get("phones") or []
            if phone and dialpad_phones != [phone]:
                contact_id = existing_contact.get("id")
                update_payload = {
                    "phones": [phone]
                }
                res = update_dialpad_contact(contact_id, update_payload)
                if res.status_code == 200:
                    print(f"🔄 Updated phone for: {first_name} {last_name}")
                else:
                    print(f"❌ Failed to update phone for {first_name} {last_name}: {res.status_code} {res.text}")
            else:
                print(f"🔁 Skipping {first_name} {last_name}, already up-to-date.")
            continue

        payload = {
            "company_id": DIALPAD_COMPANY_ID,
            "first_name": first_name,
            "last_name": last_name,
            "emails": [email] if email else [],
            "phones": [phone] if phone else []
        }

        print("➡️ Creating contact:")
        print(payload)

        res = requests.post(DIALPAD_CONTACTS_URL, headers=headers, json=payload)
        if res.status_code == 200:
            print(f"✅ Created: {first_name} {last_name}")
            added_count += 1
        else:
            print(f"❌ Failed to create {first_name} {last_name}: {res.status_code} {res.text}")

    print(f"✅ Sync complete: {added_count} new contacts added, {deleted_count} contacts deleted.")

# === Main Logic ===
if __name__ == "__main__":
    if not should_run_today():
        print(f"⏭️ SYNC_SCHEDULE is '{SYNC_SCHEDULE}'. Today doesn't match. Skipping run.")
        exit(0)

    if not all([HUBSPOT_API_KEY, DIALPAD_API_KEY, DIALPAD_COMPANY_ID]):
        print("❌ Missing one or more required environment variables. Exiting.")
        exit(1)

    hubspot_contacts = fetch_today_contacts()
    print(f"📥 Pulled {len(hubspot_contacts)} contacts from HubSpot")

    dialpad_contacts = fetch_all_shared_dialpad_contacts()
    print(f"📤 Fetched {len(dialpad_contacts)} shared contacts from Dialpad")

    email_lookup, phone_lookup = build_dialpad_lookup(dialpad_contacts)

    push_to_dialpad(hubspot_contacts, email_lookup, phone_lookup)
