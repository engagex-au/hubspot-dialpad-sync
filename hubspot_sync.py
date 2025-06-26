import os
import requests
from datetime import datetime, timezone
import pytz

# === Read config.env file ===
def read_config():
    config = {}
    try:
        with open("config.env", "r") as f:
            for line in f:
                if "=" in line:
                    key, val = line.strip().split("=", 1)
                    config[key] = val
    except FileNotFoundError:
        print("Config file not found. Exiting.")
        exit(1)
    return config

# === Schedule check ===
def should_run_sync(schedule):
    now = datetime.now(pytz.timezone('Australia/Sydney'))
    weekday = now.weekday()  # Monday=0
    day = now.day

    if schedule == "Manual (Run Now)":
        # Manual syncs are only run on-demand, so skip scheduled runs
        return False
    elif schedule == "Daily":
        return True
    elif schedule == "Weekly":
        return weekday == 0  # Monday only
    elif schedule == "Monthly":
        return day == 1      # First day of month only
    else:
        return False

# === HubSpot setup ===
def fetch_today_contacts(hubspot_api_key):
    SEARCH_URL = "https://api.hubapi.com/crm/v3/objects/contacts/search"
    HEADERS = {
        "Authorization": f"Bearer {hubspot_api_key}",
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
        "properties": ["firstname", "lastname", "email", "phone"],
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

def fetch_all_shared_dialpad_contacts(dialpad_api_key):
    url = "https://dialpad.com/api/v2/contacts"
    headers = {
        "Authorization": f"Bearer {dialpad_api_key}",
        "Content-Type": "application/json"
    }
    contacts = []
    params = {"limit": 100}
    has_more = True
    after = None

    while has_more:
        if after:
            params["cursor"] = after
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        data = res.json()

        # Filter only shared contacts
        page_contacts = [c for c in data.get("items", []) if c.get("type") == "shared"]
        contacts.extend(page_contacts)

        after = data.get("cursor")
        has_more = bool(after)

    return contacts

def build_dialpad_lookup(contacts):
    """Build lookup dict of existing emails and phones from Dialpad shared contacts."""
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

def update_dialpad_contact(contact_id, payload, dialpad_api_key):
    url = f"https://dialpad.com/api/v2/contacts/{contact_id}"
    headers = {
        "Authorization": f"Bearer {dialpad_api_key}",
        "Content-Type": "application/json"
    }
    res = requests.patch(url, headers=headers, json=payload)
    return res

def push_to_dialpad(contacts, email_lookup, phone_lookup, dialpad_api_key, company_id):
    url = "https://dialpad.com/api/v2/contacts"
    headers = {
        "Authorization": f"Bearer {dialpad_api_key}",
        "Content-Type": "application/json"
    }

    for c in contacts:
        props = c.get("properties", {})
        first_name = props.get("firstname", "")
        last_name = props.get("lastname", "")
        email = props.get("email", "").lower()
        phone = props.get("phone", "")

        if not email and not phone:
            continue

        # Decide phone type for new contact
        phone_type = "mobile" if phone.startswith("+614") else "work"

        # Check if contact exists in Dialpad by email
        existing_contact = email_lookup.get(email) if email else None

        if existing_contact:
            # Contact exists, check if phone needs update
            dialpad_phones = existing_contact.get("phones") or []
            if phone and dialpad_phones != [phone]:
                # Replace all existing numbers with the new phone number
                contact_id = existing_contact.get("id")
                update_payload = {
                    "phones": [phone]
                }
                res = update_dialpad_contact(contact_id, update_payload, dialpad_api_key)
                if res.status_code == 200:
                    print(f"🔄 Updated phone for: {first_name} {last_name}")
                else:
                    print(f"❌ Failed to update phone for {first_name} {last_name}: {res.status_code} {res.text}")
            else:
                print(f"🔁 Skipping {first_name} {last_name}, already up-to-date.")
            continue

        # If contact doesn't exist, create new one
        payload = {
            "company_id": company_id,
            "first_name": first_name,
            "last_name": last_name,
            "emails": [email] if email else [],
            "phones": [phone] if phone else []
        }

        print("➡️ Payload to Dialpad:")
        print(payload)

        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            print(f"✅ Created: {first_name} {last_name}")
        else:
            print(f"❌ Failed to create {first_name} {last_name}: {res.status_code} {res.text}")

def main():
    config = read_config()

    schedule = config.get("SYNC_SCHEDULE", "Manual (Run Now)")
    if not should_run_sync(schedule):
        print(f"Skipping sync today because schedule is '{schedule}'.")
        return

    hubspot_api_key = config.get("HUBSPOT_API_KEY")
    dialpad_api_key = config.get("DIALPAD_COOLBEANS_API_KEY")
    dialpad_company_id = config.get("DIALPAD_COMPANY_ID")

    if not (hubspot_api_key and dialpad_api_key and dialpad_company_id):
        print("Missing API keys or Company ID in config. Exiting.")
        return

    print("Running sync process...")

    try:
        hubspot_contacts = fetch_today_contacts(hubspot_api_key)
        print(f"Pulled {len(hubspot_contacts)} contacts from HubSpot")
    except Exception as e:
        print(f"Error fetching HubSpot contacts: {e}")
        return

    try:
        dialpad_contacts = fetch_all_shared_dialpad_contacts(dialpad_api_key)
        print(f"Fetched {len(dialpad_contacts)} shared contacts from Dialpad")
    except Exception as e:
        print(f"Error fetching Dialpad contacts: {e}")
        return

    email_lookup, phone_lookup = build_dialpad_lookup(dialpad_contacts)

    push_to_dialpad(
        hubspot_contacts,
        email_lookup,
        phone_lookup,
        dialpad_api_key,
        dialpad_company_id
    )

if __name__ == "__main__":
    main()
