from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, ElementNotInteractableException, TimeoutException
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os
import time
import logging
import base64
import json
import re

logging.basicConfig(level=logging.DEBUG)
logging.debug("Starting Unborn.py")

os.environ["DISPLAY"] = ":99"

# Load Google OAuth credentials from environment
CREDENTIALS_B64 = os.getenv("GOOGLE_OAUTH_CREDENTIALS_B64")
if not CREDENTIALS_B64:
    raise EnvironmentError("Google OAuth credentials not found in environment!")
credentials_json = base64.b64decode(CREDENTIALS_B64).decode('utf-8')
credentials_dict = json.loads(credentials_json)
logging.debug("Credentials successfully loaded!")

CREDENTIALS_PATH = 'credentials.json'
with open(CREDENTIALS_PATH, 'w') as creds_file:
    json.dump(credentials_dict, creds_file)

TOKEN_PATH = 'token.json'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def get_google_sheets_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logging.debug("Refreshing Google OAuth token...")
            creds.refresh(Request())
        else:
            logging.debug("Initiating new OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')

        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    return creds

# --- Setup ChromeDriver ---
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

logging.debug("Starting WebDriver")
service = Service("/usr/local/bin/chromedriver")
driver = webdriver.Chrome(service=service, options=chrome_options)
print("Chrome WebDriver successfully initialized!")

try:
    driver.set_page_load_timeout(180)
    driver.get("https://public.rma.usda.gov/livestockreports/LRPReport.aspx")
except Exception as e:
    logging.error(f"Page load failed: {e}")
    driver.quit()
    exit(1)

# --- Helper Functions ---

def select_dropdown_by_index(dropdown_id, index, attempts=5):
    for attempt in range(1, attempts + 1):
        try:
            print(f"[Attempt {attempt}] Waiting for dropdown: {dropdown_id}")
            dropdown_element = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.ID, dropdown_id))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", dropdown_element)
            dropdown = Select(dropdown_element)
            dropdown.select_by_index(index)
            time.sleep(1)
            print(f"Successfully selected index {index} from dropdown {dropdown_id}")
            return True
        except (StaleElementReferenceException, ElementNotInteractableException, TimeoutException) as e:
            print(f"Dropdown {dropdown_id} not ready yet on attempt {attempt}: {e}")
            time.sleep(2)
    print(f"Failed selecting dropdown {dropdown_id} after {attempts} attempts")
    return False

def click_button_by_name(name, attempts=5):
    for attempt in range(1, attempts + 1):
        try:
            print(f"[Attempt {attempt}] Waiting for button with name '{name}'")
            button_element = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.NAME, name))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", button_element)
            button_element.click()
            time.sleep(2)
            print(f"Clicked button '{name}'")
            return True
        except (StaleElementReferenceException, ElementNotInteractableException, TimeoutException) as e:
            print(f"Button '{name}' not ready on attempt {attempt}: {e}")
            time.sleep(2)
    print(f"Failed to click button '{name}' after {attempts} attempts")
    return False

def stop_if_failed(step):
    if not step:
        print("Critical error encountered! Stopping Script.")
        driver.quit()
        exit(1)

# --- Interact with the form ---
stop_if_failed(select_dropdown_by_index("EffectiveDate", 0))
stop_if_failed(click_button_by_name("buttonType"))

stop_if_failed(select_dropdown_by_index("StateSelection", 33))
stop_if_failed(click_button_by_name("buttonType"))

stop_if_failed(select_dropdown_by_index("CommoditySelection", 1))
stop_if_failed(click_button_by_name("buttonType"))

stop_if_failed(select_dropdown_by_index("TypeSelection", 9))
stop_if_failed(click_button_by_name("buttonType"))

time.sleep(5)

# --- Extract table data ---
try:
    report_div = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.ID, "oReportDiv"))
    )
    table = report_div.find_element(By.TAG_NAME, "table")
    WebDriverWait(driver, 10).until(
        lambda d: len(table.find_elements(By.TAG_NAME, "tr")) > 1
    )
    time.sleep(2)

    rows = table.find_elements(By.TAG_NAME, "tr")
    selected_data = []

    target_values = {13, 17, 21, 26, 30, 34, 39, 43, 47}
    found_values = {}

    for row in rows:
        cols = row.find_elements(By.TAG_NAME, "td")
        if len(cols) > 13:
            col3_text = cols[2].text.strip()
            if col3_text.isdigit():
                col3_val = int(col3_text)
                if col3_val in target_values and col3_val not in found_values:
                    def format_price(text):
                        if not text.strip(): return "N/A"
                        m = re.search(r'(\$\d{1,6}(?:\.\d{0,2})?)', text)
                        return m.group() if m else text
                    selected_data.append([
                        cols[13].text if len(cols) > 13 else "N/A",
                        format_price(cols[8].text if len(cols) > 8 else "N/A"),
                        format_price(cols[12].text if len(cols) > 12 else "N/A")
                    ])
                    found_values[col3_val] = True

    print(f"Selected Data: {selected_data}")

    # --- Push to Google Sheets ---
    service = build("sheets", "v4", credentials=get_google_sheets_service())
    spreadsheet_id = '1eFn_RVcCw3MmdLRGASrYwoCbc1UPfFNVqq1Fbz2mvYg'
    range_name = 'Sheet1!C4'
    sheet = service.spreadsheets()
    sheet.values().update(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="RAW",
        body={"values": selected_data}
    ).execute()
    print("Data successfully saved to Google Sheets!")

except Exception as e:
    print(f"Error extracting table data: {e}")

driver.quit()
logging.debug("Script finished successfully")
