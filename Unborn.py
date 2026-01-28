import requests
from bs4 import BeautifulSoup
import time
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

URL = "https://public.rma.usda.gov/livestockreports/LRPReport"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ---------------- Google Auth ----------------
CREDENTIALS_B64 = os.getenv("GOOGLE_OAUTH_CREDENTIALS_B64")
credentials_json = base64.b64decode(CREDENTIALS_B64).decode("utf-8")
with open("credentials.json", "w") as f:
    f.write(credentials_json)

def get_sheets_service():
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

# ---------------- Helpers ----------------
def extract_hidden_fields(soup):
    data = {}
    for tag in soup.select("input[type=hidden]"):
        if tag.get("name"):
            data[tag["name"]] = tag.get("value", "")
    return data

def get_first_option_value(soup, select_id):
    select = soup.find("select", {"id": select_id})
    if not select:
        raise Exception(f"Dropdown {select_id} not found")
    option = select.find("option")
    return option.get("value", "")

# ---------------- Start Session ----------------
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Referer": URL
})

# -------- Step 1: Load page --------
resp = session.get(URL)
resp.raise_for_status()
soup = BeautifulSoup(resp.text, "html.parser")

form_data = extract_hidden_fields(soup)

# -------- Step 2: Effective Date (most recent = first option) --------
form_data["EffectiveDate"] = get_first_option_value(soup, "EffectiveDate")
form_data["buttonType"] = "Next >>"

resp = session.post(URL, data=form_data)
resp.raise_for_status()
soup = BeautifulSoup(resp.text, "html.parser")
form_data = extract_hidden_fields(soup)

# -------- Step 3: State (fixed) --------
form_data["StateSelection"] = "38|North Dakota"
form_data["buttonType"] = "Next >>"

resp = session.post(URL, data=form_data)
resp.raise_for_status()
soup = BeautifulSoup(resp.text, "html.parser")
form_data = extract_hidden_fields(soup)

# -------- Step 4: Commodity (fixed) --------
form_data["CommoditySelection"] = "0801|Feeder Cattle"
form_data["buttonType"] = "Next >>"

resp = session.post(URL, data=form_data)
resp.raise_for_status()
soup = BeautifulSoup(resp.text, "html.parser")
form_data = extract_hidden_fields(soup)

# -------- Step 5: Type (fixed) --------
form_data["TypeSelection"] = "817|Unborn Bulls & Heifers"
form_data["buttonType"] = "Create Report"

resp = session.post(URL, data=form_data)
resp.raise_for_status()
soup = BeautifulSoup(resp.text, "html.parser")

# ---------------- Parse Table ----------------
table_div = soup.find("div", {"id": "oReportDiv"})
if not table_div:
    raise Exception("Report table not found on page")

table = table_div.find("table")
rows = table.find_all("tr")
selected_data = []

target_values = {13, 17, 21, 26, 30, 34, 39, 43, 47}
found = set()

for row in rows:
    cols = row.find_all("td")
    if len(cols) > 13:
        val = cols[2].get_text(strip=True)
        if val.isdigit() and int(val) in target_values and int(val) not in found:
            def price(col):
                txt = col.get_text(strip=True)
                m = re.search(r"\$\d+(?:\.\d{2})?", txt)
                return m.group() if m else "N/A"

            selected_data.append([
                cols[13].get_text(strip=True),
                price(cols[8]),
                price(cols[12])
            ])
            found.add(int(val))

logging.info(f"Collected {len(selected_data)} rows")

# ---------------- Write to Google Sheets ----------------
service = get_sheets_service()
sheet = service.spreadsheets()

sheet.values().update(
    spreadsheetId="1eFn_RVcCw3MmdLRGASrYwoCbc1UPfFNVqq1Fbz2mvYg",
    range="Sheet1!C4",
    valueInputOption="RAW",
    body={"values": selected_data}
).execute()

logging.info("Upload complete")
