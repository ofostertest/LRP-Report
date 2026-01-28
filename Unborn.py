import os
import json
import base64
import time
import logging
import re

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ------------------- Logging -------------------
logging.basicConfig(level=logging.DEBUG)
logging.debug("Starting Unborn.py")

# ------------------- Environment -------------------
os.environ["DISPLAY"] = ":99"

CREDENTIALS_B64 = os.getenv("GOOGLE_OAUTH_CREDENTIALS_B64")
if not CREDENTIALS_B64:
    raise EnvironmentError("Google OAuth credentials not found in environment!")

credentials_json = base64.b64decode(CREDENTIALS_B64).decode("utf-8")
credentials_dict = json.loads(credentials_json)

CREDENTIALS_PATH = "credentials.json"
with open(CREDENTIALS_PATH, "w") as f:
    json.dump(credentials_dict, f)

TOKEN_PATH = "token.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ------------------- Google Sheets -------------------
def get_google_sheets_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logging.debug("Refreshing Google OAuth token...")
            creds.refresh(Request())
        else:
            logging.debug("Starting new OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')

        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    return creds

# ------------------- Chrome WebDriver -------------------
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

logging.debug("Starting Chrome WebDriver")
service = Service("/usr/local/bin/chromedriver")
driver = webdriver.Chrome(service=service, options=chrome_options)
logging.debug("Chrome WebDriver successfully initialized!")

# ------------------- Utilities -------------------
def stop_if_failed(success, msg="Critical error"):
    if not success:
        logging.error(msg)
        driver.quit()
        exit(1)

def select_dropdown(dropdown_id, option_index=0, timeout=15):
    """Select an option from a real <select> dropdown by index."""
    try:
        logging.debug(f"Waiting for dropdown: {dropdown_id}")
        select_elem = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.ID, dropdown_id))
        )

        # Wait until the <select> is visible and enabled
        WebDriverWait(driver, timeout).until(
            lambda d: select_elem.is_displayed() and select_elem.is_enabled()
        )

        # Ensure options are loaded
        options = WebDriverWait(driver, timeout).until(
            lambda d: select_elem.find_elements(By.TAG_NAME, "option")
        )
        if not options:
            raise Exception(f"No options found for {dropdown_id}")

        dropdown = Select(select_elem)
        dropdown.select_by_index(option_index)
        time.sleep(0.5)
        logging.debug(f"Selected option index {option_index} from {dropdown_id}")
        return True

    except Exception as e:
        logging.error(f"Failed selecting dropdown {dropdown_id}: {e}")
        return False

def click_next_button(timeout=10):
    """Click the 'Next >>' button."""
    try:
        button = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Next >>']"))
        )
        button.click()
        time.sleep(1)
        logging.debug("Clicked 'Next >>' button")
        return True
    except Exception as e:
        logging.error(f"Failed clicking 'Next >>' button: {e}")
        return False

# ------------------- Navigate to LRP page -------------------
try:
    driver.set_page_load_timeout(180)
    driver.get("https://public.rma.usda.gov/livestockreports/LRPReport.aspx")
except Exception as e:
    logging.error(f"Page load failed: {e}")
    driver.quit()
    exit(1)

# ------------------- Select Dropdowns -------------------
stop_if_failed(select_dropdown("EffectiveDate", 0))
stop_if_failed(click_next_button())

stop_if_failed(select_dropdown("StateSelection", 33))
stop_if_failed(click_next_button())

stop_if_failed(select_dropdown("CommoditySelection", 1))
stop_if_failed(click_next_button())

stop_if_failed(select_dropdown("TypeSelection", 9))
stop_if_failed(click_next_button())

time.sleep(2)  # Wait for table to render

# ------------------- Extract Table Data -------------------
try:
    table_div = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.ID, "oReportDiv"))
    )
    table = table_div.find_element(By.TAG_NAME, "table")
    rows = table.find_elements(By.TAG_NAME, "tr")
    selected_data = []

    target_values = {13, 17, 21, 26, 30, 34, 39, 43, 47}
    found_values = {}

    for row in rows:
        cols = row.find_elements(By.TAG_NAME, "td")
        if len(cols) > 13:
            column_3_value = cols[2].text.strip()
            if column_3_value.isdigit():
                column_3_int = int(column_3_value)
                if column_3_int in target_values and column_3_int not in found_values:
                    raw_price_8 = cols[8].text.strip() if len(cols) > 8 else "N/A"
                    raw_price_12 = cols[12].text.strip() if len(cols) > 12 else "N/A"

                    def format_price(price_text):
                        if not price_text.strip():
                            return "N/A"
                        match = re.search(r'(\$\d{1,6}(?:\.\d{0,2})?)', price_text)
                        return match.group() if match else price_text

                    formatted_price_8 = format_price(raw_price_8)
                    formatted_price_12 = format_price(raw_price_12)

                    selected_data.append([
                        cols[13].text if len(cols) > 13 else "N/A",
                        formatted_price_8,
                        formatted_price_12
                    ])

                    found_values[column_3_int] = True

    logging.debug(f"Selected Data: {selected_data}")

    # ------------------- Update Google Sheets -------------------
    service = build("sheets", "v4", credentials=get_google_sheets_service())
    spreadsheet_id = "1eFn_RVcCw3MmdLRGASrYwoCbc1UPfFNVqq1Fbz2mvYg"
    range_name = "Sheet1!C4"
    sheet = service.spreadsheets()
    sheet.values().update(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="RAW",
        body={"values": selected_data}
    ).execute()
    logging.debug("Data successfully saved to Google Sheets!")

except Exception as e:
    logging.error(f"Error extracting table data: {e}")

driver.quit()
logging.debug("Script finished successfully")
