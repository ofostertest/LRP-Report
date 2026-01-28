import os
import base64
import logging
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logging.basicConfig(level=logging.INFO)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SPREADSHEET_ID = "1eFn_RVcCw3MmdLRGASrYwoCbc1UPfFNVqq1Fbz2mvYg"
SHEET_NAME = "Sheet1"

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

# ---------------- Update Timestamp Logic ----------------
def update_timestamp_if_data_exists():
    service = get_sheets_service()

    # Range that contains report data
    data_range = f"{SHEET_NAME}!C4:G58"
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=data_range
    ).execute()

    data = result.get("values", [])

    # Check if ANY cell has data
    changes_detected = any(any(cell.strip() for cell in row) for row in data)

    if changes_detected:
        now = datetime.now().strftime("%m-%d-%Y")
        timestamp_range = f"{SHEET_NAME}!D1"

        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=timestamp_range,
            valueInputOption="RAW",
            body={"values": [[now]]}
        ).execute()

        logging.info(f"Timestamp updated in D1: {now}")
    else:
        logging.info("No data detected — timestamp not updated")

# ---------------- Run ----------------
update_timestamp_if_data_exists()
logging.info("MDY script finished successfully")
