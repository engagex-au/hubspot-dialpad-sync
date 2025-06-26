import os
import requests

HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY")
API_URL = "https://api.hubapi.com/crm/v3/objects/contacts"

HEADERS = {
    "Authorization": f"Bearer {HUBSPOT_API_KEY}",
    "Content-Type": "application/json"
}

params = {
    "limit": 100,
    "properties": "firstname,lastname,email,phone"
}

def fetch_contacts():
    contacts = []
    has_more = True
    after = None

    while has_more:
        if after:
            params["after"] = after
        res = requests.get(API_URL, headers=HEADERS, params=params)
        res.raise_for_status()
        data = res.json()
        contacts.extend(data.get("results", []))
        paging = data.get("paging")
        after = paging.get("next", {}).get("after") if paging else None
        has_more = bool(after)

    return contacts

if __name__ == "__main__":
    contacts = fetch_contacts()
    for c in contacts:
        props = c["properties"]
        print(f"{props.get('firstname', '')} {props.get('lastname', '')} | {props.get('email', '')} | {props.get('phone', '')}")
