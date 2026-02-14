import requests
from bs4 import BeautifulSoup
import re
import os
import json
import base64
import logging
import time
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from requests.exceptions import HTTPError

logging.basicConfig(level=logging.INFO)

URL = "https://public.rma.usda.gov/livestockreports/LRPReport"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SPREADSHEET_ID = "1eFn_RVcCw3MmdLRGASrYwoCbc1UPfFNVqq1Fbz2mvYg"

STATE_VALUE = "38|North Dakota"
COMMODITY_VALUE = "0801|Feeder Cattle"
TYPE_VALUE = "809|Steers Weight 1"

TARGET_VALUES = {13, 17, 21, 26, 30, 34, 39, 43, 47}

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
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
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

def post_with_retry(session, url, data, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(url, data=data)
            resp.raise_for_status()
            return resp
        except HTTPError as e:
            logging.warning(f"POST attempt {attempt} failed: {e}")
            if attempt == max_retries:
                raise
            time.sleep(2)

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

# -------- Step 2: Effective Date --------
form_data["EffectiveDate"] = get_first_option_value(soup, "EffectiveDate")
form_data["buttonType"] = "Next >>"
resp = post_with_retry(session, URL, form_data)
soup = BeautifulSoup(resp.text, "html.parser")
form_data = extract_hidden_fields(soup)

# -------- Step 3: State --------
form_data["StateSelection"] = "38|North Dakota"
form_data["buttonType"] = "Next >>"
resp = post_with_retry(session, URL, form_data)
soup = BeautifulSoup(resp.text, "html.parser")
form_data = extract_hidden_fields(soup)

# -------- Step 4: Commodity --------
form_data["CommoditySelection"] = "0801|Feeder Cattle"
form_data["buttonType"] = "Next >>"
resp = post_with_retry(session, URL, form_data)
soup = BeautifulSoup(resp.text, "html.parser")
form_data = extract_hidden_fields(soup)

# -------- Step 5: Type --------
form_data["TypeSelection"] = "812|Heifers Weight 2"
form_data["buttonType"] = "Create Report"
resp = post_with_retry(session, URL, form_data)
soup = BeautifulSoup(resp.text, "html.parser")

# ---------------- Parse All Tables ----------------
tables = soup.find_all("table")  # Search all tables on the page
selected_data = []
found = set()  # Track which target values have been found

TARGET_VALUES = {13, 17, 21, 26, 30, 34, 39, 43, 47}

def price(col):
    txt = col.get_text(strip=True)
    m = re.search(r"\$\d+(?:\.\d{2})?", txt)
    return m.group() if m else "N/A"

for table in tables:
    rows = table.find_all("tr")
    for row in rows:
        cols = row.find_all("td")
        if len(cols) > 13:
            val = cols[2].get_text(strip=True)
            if val.isdigit():
                val_int = int(val)
                if val_int in TARGET_VALUES and val_int not in found:
                    selected_data.append([
                        cols[13].get_text(strip=True),  # Column 13
                        price(cols[8]),                 # Column 8
                        cols[12].get_text(strip=True)   # Column 12
                    ])
                    found.add(val_int)

if len(selected_data) < len(TARGET_VALUES):
    logging.warning(f"Only collected {len(selected_data)} rows out of {len(TARGET_VALUES)} target values")
else:
    logging.info(f"Collected all {len(selected_data)} rows")

logging.info("Selected Data:")
for row in selected_data:
    logging.info(row)

# ---------------- Write to Google Sheets ----------------
service = get_sheets_service()
sheet = service.spreadsheets()

sheet.values().update(
    spreadsheetId=SPREADSHEET_ID,
    range="Sheet1!C50",
    valueInputOption="RAW",
    body={"values": selected_data}
).execute()

logging.info("Upload complete")
