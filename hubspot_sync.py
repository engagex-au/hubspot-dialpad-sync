import os
import requests
from datetime import datetime, timezone
import pytz

# === HubSpot setup ===
HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY")
SEARCH_URL = "https://api.hubapi.com/crm/v3/objects/contacts/search"
HEADERS = {
    "Authorization": f"Bearer {HUBSPOT_API_KEY}",
    "Content-Type": "application/json"
}

def fetch_today_contacts():
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


def fetch_all_shared_dialpad_contacts():
    DIALPAD_API_KEY = os.getenv("DIALPAD_COOLBEANS_API_KEY")
    url = "https://dialpad.com/api/v2/contacts"
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

def update_dialpad_contact(contact_id, payload):
    DIALPAD_API_KEY = os.getenv("DIALPAD_COOLBEANS_API_KEY")
    url = f"https://dialpad.com/api/v2/contacts/{contact_id}"
    headers = {
        "Authorization": f"Bearer {DIALPAD_API_KEY}",
        "Content-Type": "application/json"
    }
    res = requests.patch(url, headers=headers, json=payload)
    return res

def push_to_dialpad(contacts, email_lookup, phone_lookup):
    DIALPAD_API_KEY = os.getenv("DIALPAD_COOLBEANS_API_KEY")
    COMPANY_ID = os.getenv("DIALPAD_COMPANY_ID")

    if not DIALPAD_API_KEY:
        raise ValueError("❌ DIALPAD_COOLBEANS_API_KEY not set in environment")

    url = "https://dialpad.com/api/v2/contacts"
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

        if not email and not phone:
            continue

        # Decide phone type for new contact
        phone_type = "mobile" if phone.startswith("+614") else "work"

        # Check if contact exists in Dialpad by email
        existing_contact = email_lookup.get(email) if email else None

        if existing_contact:
            # Contact exists, check if phone needs update
            dialpad_phones = existing_contact.get("phones") or []
            if phone and phone not in dialpad_phones:
                # Update Dialpad contact with new phone
                contact_id = existing_contact.get("id")
                update_payload = {
                    "phones": dialpad_phones + [phone]  # append new phone
                }
                res = update_dialpad_contact(contact_id, update_payload)
                if res.status_code == 200:
                    print(f"🔄 Updated phone for: {first_name} {last_name}")
                else:
                    print(f"❌ Failed to update phone for {first_name} {last_name}: {res.status_code} {res.text}")
            else:
                print(f"🔁 Skipping {first_name} {last_name}, already up-to-date.")
            continue

        # If contact doesn't exist, create new one
        payload = {
            "company_id": COMPANY_ID,
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


if __name__ == "__main__":
    # Fetch HubSpot contacts created today
    hubspot_contacts = fetch_today_contacts()
    print(f"Pulled {len(hubspot_contacts)} contacts from HubSpot")

    # Fetch all Dialpad shared contacts for deduplication and updates
    dialpad_shared_contacts = fetch_all_shared_dialpad_contacts()
    print(f"Fetched {len(dialpad_shared_contacts)} shared contacts from Dialpad")

    email_lookup, phone_lookup = build_dialpad_lookup(dialpad_shared_contacts)

    # Push new or updated contacts to Dialpad
    push_to_dialpad(hubspot_contacts, email_lookup, phone_lookup)
