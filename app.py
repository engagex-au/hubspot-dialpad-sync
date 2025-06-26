import streamlit as st
import requests
import os
from datetime import datetime, timezone
import pytz

# === Core Functions ===
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
        else:
            params.pop("cursor", None)

        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        data = res.json()

        page_contacts = [c for c in data.get("items", []) if c.get("type") == "shared"]
        contacts.extend(page_contacts)

        after = data.get("cursor")
        has_more = bool(after)

    return contacts

def build_dialpad_lookup(contacts):
    emails = set()
    phones = set()

    for c in contacts:
        for email in c.get("emails") or []:
            emails.add(email.lower())
        for phone in c.get("phones") or []:
            phones.add(phone)

    return emails, phones

def push_to_dialpad(contacts, dialpad_api_key, dialpad_company_id, dialpad_emails, dialpad_phones):
    url = "https://dialpad.com/api/v2/contacts"
    headers = {
        "Authorization": f"Bearer {dialpad_api_key}",
        "Content-Type": "application/json"
    }

    added_count = 0

    for c in contacts:
        props = c.get("properties", {})
        first_name = props.get("firstname", "")
        last_name = props.get("lastname", "")
        email = props.get("email", "").lower()
        phone = props.get("phone", "")

        if not email and not phone:
            continue

        if email in dialpad_emails or phone in dialpad_phones:
            st.write(f"🔁 Skipping duplicate: {first_name} {last_name}")
            continue

        payload = {
            "company_id": dialpad_company_id,
            "first_name": first_name,
            "last_name": last_name,
            "emails": [email] if email else [],
            "phones": [phone] if phone else []
        }

        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            st.write(f"✅ Upserted: {first_name} {last_name}")
            added_count += 1
        else:
            st.error(f"❌ Failed for {first_name} {last_name}: {res.status_code} {res.text}")

    return added_count

# === Streamlit Frontend ===
def main():
    st.title("HubSpot to Dialpad Contact Sync")

    hubspot_api_key = st.text_input("🔑 HubSpot API Key", type="password")
    dialpad_api_key = st.text_input("🔐 Dialpad API Key", type="password")
    dialpad_company_id = st.text_input("🏢 Dialpad Company ID")

    sync_schedule = st.selectbox("📅 Sync Schedule", ["Manual (Run Now)", "Daily", "Weekly", "Monthly"])

    if st.button("💾 Save Configuration"):
        with open("config.env", "w") as f:
            f.write(f"HUBSPOT_API_KEY={hubspot_api_key}\n")
            f.write(f"DIALPAD_COOLBEANS_API_KEY={dialpad_api_key}\n")
            f.write(f"DIALPAD_COMPANY_ID={dialpad_company_id}\n")
            f.write(f"SYNC_SCHEDULE={sync_schedule}\n")

        next_run_time = None
        if sync_schedule == "Daily":
            next_run_time = "tomorrow at 2:00 AM AEST"
        elif sync_schedule == "Weekly":
            next_run_time = "next Monday at 2:00 AM AEST"
        elif sync_schedule == "Monthly":
            next_run_time = "the 1st of next month at 2:00 AM AEST"

        if next_run_time:
            st.success(f"✅ Configuration saved! Sync will run {next_run_time}.")
        else:
            st.success("✅ Configuration saved!")

    if sync_schedule == "Manual (Run Now)":
        if st.button("🚀 Run Sync Now"):
            if not (hubspot_api_key and dialpad_api_key and dialpad_company_id):
                st.error("❌ Please enter all API keys and Company ID")
                return

            try:
                st.info("📥 Fetching contacts from HubSpot...")
                hubspot_contacts = fetch_today_contacts(hubspot_api_key)
                st.write(f"Pulled {len(hubspot_contacts)} contacts from HubSpot")
            except Exception as e:
                st.error(f"❌ Error fetching HubSpot contacts: {e}")
                return

            try:
                st.info("📤 Fetching shared contacts from Dialpad...")
                dialpad_contacts = fetch_all_shared_dialpad_contacts(dialpad_api_key)
                st.write(f"Fetched {len(dialpad_contacts)} shared contacts from Dialpad")
            except Exception as e:
                st.error(f"❌ Error fetching Dialpad contacts: {e}")
                return

            dialpad_emails, dialpad_phones = build_dialpad_lookup(dialpad_contacts)

            st.info("🔄 Syncing new contacts...")
            added = push_to_dialpad(
                hubspot_contacts,
                dialpad_api_key,
                dialpad_company_id,
                dialpad_emails,
                dialpad_phones
            )

            st.success(f"✅ Sync complete: {added} new contacts added.")

if __name__ == "__main__":
    main()
