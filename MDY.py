import requests
from bs4 import BeautifulSoup
import os
import base64
import logging
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logging.basicConfig(level=logging.INFO)

URL = "https://public.rma.usda.gov/livestockreports/LRPReport"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SPREADSHEET_ID = "1eFn_RVcCw3MmdLRGASrYwoCbc1UPfFNVqq1Fbz2mvYg"
TARGET_RANGE = "Sheet1!D1"

# ---------------- Google Auth ----------------
CREDENTIALS_B64 = os.getenv("GOOGLE_OAUTH_CREDENTIALS_B64")
if not CREDENTIALS_B64:
    raise Exception("Missing GOOGLE_OAUTH_CREDENTIALS_B64 environment variable")

with open("credentials.json", "w") as f:
    f.write(base64.b64decode(CREDENTIALS_B64).decode("utf-8"))

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

# ---------------- Fetch First Effective Date ----------------
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0"
})

resp = session.get(URL)
resp.raise_for_status()

soup = BeautifulSoup(resp.text, "html.parser")

effective_date_select = soup.find("select", {"id": "EffectiveDate"})
if not effective_date_select:
    raise Exception("EffectiveDate dropdown not found")

first_option = effective_date_select.find("option")
if not first_option:
    raise Exception("No options found in EffectiveDate dropdown")

first_effective_date = first_option.get_text(strip=True)
logging.info(f"Most recent effective date: {first_effective_date}")

# ---------------- Write to Google Sheets ----------------
service = get_sheets_service()
sheet = service.spreadsheets()

sheet.values().update(
    spreadsheetId=SPREADSHEET_ID,
    range=TARGET_RANGE,
    valueInputOption="RAW",
    body={"values": [[first_effective_date]]}
).execute()

logging.info("Effective date successfully written to Google Sheets")
