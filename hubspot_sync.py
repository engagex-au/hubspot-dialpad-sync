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


def push_to_dialpad(contacts):
    DIALPAD_API_KEY = os.getenv("DIALPAD_COOLBEANS_API_KEY")  # 🔁 correct secret name
    COMPANY_ID = os.getenv("DIALPAD_COMPANY_ID")

    url = "https://dialpad.com/api/v2/contacts"
    headers = {
        "Authorization": f"Bearer {DIALPAD_API_KEY}",
        "Content-Type": "application/json"
    }

    for c in contacts:
        props = c.get("properties", {})
        first_name = props.get("firstname", "")
        last_name = props.get("lastname", "")
        email = props.get("email", "")
        phone = props.get("phone", "")

        if not email and not phone:
            continue

        payload = {
            "company_id": COMPANY_ID,
            "first_name": first_name,
            "last_name": last_name,
            "emails": [{"type": "work", "value": email}] if email else [],
            "phone_numbers": [{"type": "work", "value": phone}] if phone else []
        }

        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            print(f"✅ Upserted: {first_name} {last_name}")
        else:
            print(f"❌ Failed for {first_name} {last_name}: {res.status_code} {res.text}")


# ✅ Final and only main block
if __name__ == "__main__":
    contacts = fetch_today_contacts()
    print(f"Pulled {len(contacts)} contacts from HubSpot")

    # Optional: print for debug
    for c in contacts:
        props = c["properties"]
        print(f"{props.get('firstname', '')} {props.get('lastname', '')} | {props.get('email', '')} | {props.get('phone', '')}")

    push_to_dialpad(contacts)
