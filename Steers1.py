import requests
from bs4 import BeautifulSoup
import os
import base64
import re
import logging
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logging.basicConfig(level=logging.INFO)

URL = "https://public.rma.usda.gov/livestockreports/LRPReport"
SPREADSHEET_ID = "1eFn_RVcCw3MmdLRGASrYwoCbc1UPfFNVqq1Fbz2mvYg"
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

def extract_hidden_fields(soup):
    data = {}
    for tag in soup.select("input[type=hidden]"):
        if tag.get("name"):
            data[tag["name"]] = tag.get("value", "")
    return data

form_data = extract_hidden_fields(soup)
form_data["EffectiveDate"] = soup.find("select", {"id": "EffectiveDate"}).find("option").get("value")
form_data["buttonType"] = "Next >>"

# -------- Step 2: State Selection --------
form_data["StateSelection"] = "38|North Dakota"
form_data["buttonType"] = "Next >>"
resp = session.post(URL, data=form_data)
resp.raise_for_status()
soup = BeautifulSoup(resp.text, "html.parser")
form_data = extract_hidden_fields(soup)

# -------- Step 3: Commodity Selection --------
form_data["CommoditySelection"] = "0801|Feeder Cattle"
form_data["buttonType"] = "Next >>"
resp = session.post(URL, data=form_data)
resp.raise_for_status()
soup = BeautifulSoup(resp.text, "html.parser")
form_data = extract_hidden_fields(soup)

# -------- Step 4: Type Selection --------
form_data["TypeSelection"] = "809|Steers Weight 1"
form_data["buttonType"] = "Create Report"
resp = session.post(URL, data=form_data)
resp.raise_for_status()
soup = BeautifulSoup(resp.text, "html.parser")

# ---------------- Parse All Tables ----------------
table_div = soup.find("div", {"id": "oReportDiv"})
if not table_div:
    raise Exception("Report table not found on page")

tables = table_div.find_all("table", recursive=True)
selected_data = []
found = set()
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
                        cols[11].get_text(strip=True)   # Column 11
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
    range="Sheet1!C15",  # Adjust range for Steers1
    valueInputOption="RAW",
    body={"values": selected_data}
).execute()

logging.info("Upload complete")
