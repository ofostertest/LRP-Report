import requests
from bs4 import BeautifulSoup
import re
import os
import json
import base64
import logging
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logging.basicConfig(level=logging.INFO)

BASE_URL = "https://public.rma.usda.gov/livestockreports/LRPReport.aspx"

# ------------------ Google Sheets ------------------

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CREDENTIALS_B64 = os.getenv("GOOGLE_OAUTH_CREDENTIALS_B64")

credentials_json = base64.b64decode(CREDENTIALS_B64).decode("utf-8")
with open("credentials.json", "w") as f:
    f.write(credentials_json)

def get_google_sheets_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("sheets", "v4", credentials=creds)

# ------------------ ASP.NET helpers ------------------

def extract_hidden_fields(soup):
    data = {}
    for tag in soup.select("input[type='hidden']"):
        data[tag.get("name")] = tag.get("value", "")
    return data

def post_form(session, soup, updates):
    payload = extract_hidden_fields(soup)
    payload.update(updates)
    response = session.post(BASE_URL, data=payload)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")

# ------------------ Scraper ------------------

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0"
})

# Step 1: Initial page
resp = session.get(BASE_URL)
resp.raise_for_status()
soup = BeautifulSoup(resp.text, "html.parser")

# ---- Effective Date (first option) ----
effective_options = soup.select("#EffectiveDate option")
effective_value = effective_options[1]["value"]  # skip empty option

soup = post_form(session, soup, {
    "EffectiveDate": effective_value,
    "buttonType": "Next >>"
})

# ---- State ----
state_options = soup.select("#StateSelection option")
state_value = state_options[33]["value"]

soup = post_form(session, soup, {
    "StateSelection": state_value,
    "buttonType": "Next >>"
})

# ---- Commodity ----
commodity_options = soup.select("#CommoditySelection option")
commodity_value = commodity_options[1]["value"]

soup = post_form(session, soup, {
    "CommoditySelection": commodity_value,
    "buttonType": "Next >>"
})

# ---- Type ----
type_options = soup.select("#TypeSelection option")
type_value = type_options[9]["value"]

soup = post_form(session, soup, {
    "TypeSelection": type_value,
    "buttonType": "Next >>"
})

# ------------------ Parse Table ------------------

table = soup.select_one("#oReportDiv table")
rows = table.select("tr")

target_values = {13, 17, 21, 26, 30, 34, 39, 43, 47}
selected_data = []
found = set()

def extract_price(text):
    match = re.search(r"\$\d+(?:\.\d{1,2})?", text)
    return match.group() if match else "N/A"

for row in rows:
    cols = [c.get_text(strip=True) for c in row.select("td")]
    if len(cols) < 14:
        continue

    if cols[2].isdigit():
        val = int(cols[2])
        if val in target_values and val not in found:
            selected_data.append([
                cols[13],
                extract_price(cols[8]),
                extract_price(cols[12]),
            ])
            found.add(val)

print("Selected Data:")
for r in selected_data:
    print(r)

# ------------------ Google Sheets Update ------------------

service = get_google_sheets_service()
sheet = service.spreadsheets()

sheet.values().update(
    spreadsheetId="1eFn_RVcCw3MmdLRGASrYwoCbc1UPfFNVqq1Fbz2mvYg",
    range="Sheet1!C4",
    valueInputOption="RAW",
    body={"values": selected_data}
).execute()

print("✅ Data successfully written to Google Sheets")
