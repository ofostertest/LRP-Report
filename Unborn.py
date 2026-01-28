from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os
import json
import base64
import time
import logging
import re

logging.basicConfig(level=logging.DEBUG)
logging.debug("Starting Unborn.py")

os.environ["DISPLAY"] = ":99"

# --- Google OAuth Setup ---
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

# --- Chrome Setup ---
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

logging.debug("Starting Chrome WebDriver")
service = Service("/usr/local/bin/chromedriver")
driver = webdriver.Chrome(service=service, options=chrome_options)
print("Chrome WebDriver successfully initialized!")

# --- Utility Functions ---
def stop_if_failed(step, msg="Critical error"):
    if not step:
        print(f"{msg}! Stopping script.")
        driver.quit()
        exit(1)

def select_dropdown_by_id(dropdown_id, index, max_attempts=5):
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"[Attempt {attempt}] Waiting for dropdown: {dropdown_id}")
            dropdown_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, dropdown_id))
            )
            if not dropdown_element.is_displayed():
                raise Exception("Dropdown not visible yet")
            
            dropdown = Select(dropdown_element)
            dropdown.select_by_index(index)
            
            # Trigger JS change in case of postback
            driver.execute_script(
                "arguments[0].dispatchEvent(new Event('change'))", dropdown_element
            )
            time.sleep(1)
            print(f"Successfully selected index {index} from {dropdown_id}")
            return True
        except Exception as e:
            print(f"Dropdown {dropdown_id} not ready yet on attempt {attempt}: {e}")
            time.sleep(1)
    print(f"Failed selecting dropdown {dropdown_id} after {max_attempts} attempts")
    return False

def click_next_button():
    try:
        button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//input[@type='submit' and @value='Next >>']")
            )
        )
        button.click()
        time.sleep(1)
        print("Clicked 'Next >>' button")
        return True
    except Exception as e:
        print(f"Error clicking 'Next >>' button: {e}")
        return False

# --- Navigate to LRP page ---
try:
    driver.set_page_load_timeout(180)
    driver.get("https://public.rma.usda.gov/livestockreports/LRPReport.aspx")
except Exception as e:
    logging.error(f"Page load failed: {e}")
    driver.quit()
    exit(1)

# --- Select Dropdowns and Click Next ---
stop_if_failed(select_dropdown_by_id("EffectiveDate", 0))
stop_if_failed(click_next_button())

stop_if_failed(select_dropdown_by_id("StateSelection", 33))
stop_if_failed(click_next_button())

stop_if_failed(select_dropdown_by_id("CommoditySelection", 1))
stop_if_failed(click_next_button())

stop_if_failed(select_dropdown_by_id("TypeSelection", 9))
stop_if_failed(click_next_button())

time.sleep(5)

# --- Extract Table Data ---
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

    print(f"Selected Data: {selected_data}")

    # --- Update Google Sheets ---
    service = build("sheets", "v4", credentials=get_google_sheets_service())
    spreadsheet_id = "1eFn_RVcCw3MmdLRGASrYwoCbc1UPfFNVqq1Fbz2mvYg"
    range_name = "Sheet1!C4"
    sheet = service.spreadsheets()
    update_values = selected_data
    sheet.values().update(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="RAW",
        body={"values": update_values}
    ).execute()
    print("Data successfully saved to Google Sheets!")

except Exception as e:
    print(f"Error extracting table data: {e}")

driver.quit()
logging.debug("Script finished successfully")
