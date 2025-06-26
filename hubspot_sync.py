import os
import requests

HUBSPOT_API_KEY = os.getenv("pat-na2-258f7834-e46b-47eb-9c7e-d82cd5d64fa2")

HUBSPOT_API_URL = "https://api.hubapi.com/crm/v3/objects/contacts"
HEADERS = {
    "Authorization": f"Bearer {HUBSPOT_API_KEY}",
    "Content-Type": "application/json"
}
params = {
    "limit": 100,
    "properties": "firstname,lastname,email,phone"
}

def fetch_all_contacts():
    contacts = []
    has_more = True
    after = None

    while has_more:
        if after:
            params["after"] = after

        response = requests.get(HUBSPOT_API_URL, headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json()

        contacts.extend(data.get("results", []))
        paging = data.get("paging")
        if paging and "next" in paging:
            after = paging["next"]["after"]
        else:
            has_more = False

    return contacts

if __name__ == "__main__":
    contacts = fetch_all_contacts()
    for c in contacts:
        props = c["properties"]
        print(f"{props.get('firstname')} {props.get('lastname')} - {props.get('email')} - {props.get('phone')}")
