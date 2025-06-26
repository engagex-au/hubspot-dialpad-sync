import os
import requests
from datetime import datetime, timedelta, timezone
import pytz

HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY")
SEARCH_URL = "https://api.hubapi.com/crm/v3/objects/contacts/search"

HEADERS = {
    "Authorization": f"Bearer {HUBSPOT_API_KEY}",
    "Content-Type": "application/json"
}

def fetch_today_contacts():
    # Set timezone to AEST (UTC+10) — use Australia/Sydney for automatic daylight handling
    aest = pytz.timezone('Australia/Sydney')

    # Get current date at 00:00 AEST
    now_aest = datetime.now(aest)
    start_of_day_aest = now_aest.replace(hour=0, minute=0, second=0, microsecond=0)

    # Convert to UTC for HubSpot
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

if __name__ == "__main__":
    contacts = fetch_today_contacts()
    for c in contacts:
        props = c["properties"]
        print(f"{props.get('firstname', '')} {props.get('lastname', '')} | {props.get('email', '')} | {props.get('phone', '')}")
