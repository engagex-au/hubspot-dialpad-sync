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
    params = {
        "limit": 100,
        "include_local": "false"
    }
    cursor = None

    while True:
        if cursor:
            params["cursor"] = cursor

        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        data = res.json()

        shared_contacts = [c for c in data.get("items", []) if c.get("type") == "shared"]
        contacts.extend(shared_contacts)

        cursor = data.get("cursor")
        if not cursor:
            break

    return contacts

def build_dialpad_lookup(contacts):
    emails = set()
    phones = set()

    for c in contacts:
        for email in c.get("emails", []) or []:
            if email:
                emails.add(email.strip().lower())
        for phone in c.get("phones", []) or []:
            if phone:
                phones.add(phone.strip())

    return emails, phones

def push_to_dialpad(contacts, dialpad_emails, dialpad_phones):
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
        email = props.get("email", "").strip().lower()
        phone = props.get("phone", "").strip()

        if not email and not phone:
            continue

        if email in dialpad_emails or phone in dialpad_phones:
            print(f"🔁 Skipping duplicate: {first_name} {last_name}")
            continue

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
            print(f"✅ Upserted: {first_name} {last_name}")
        else:
            print(f"❌ Failed for {first_name} {last_name}: {res.status_code} {res.text}")

# === Main block
if __name__ == "__main__":
    hubspot_contacts = fetch_today_contacts()
    print(f"Pulled {len(hubspot_contacts)} contacts from HubSpot")

    dialpad_contacts = fetch_all_shared_dialpad_contacts()
    print(f"Fetched {len(dialpad_contacts)} shared contacts from Dialpad")

    dialpad_emails, dialpad_phones = build_dialpad_lookup(dialpad_contacts)

    push_to_dialpad(hubspot_contacts, dialpad_emails, dialpad_phones)
