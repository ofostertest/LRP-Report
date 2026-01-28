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
import re
import time
import logging
import base64
import json

logging.basicConfig(level=logging.DEBUG)
logging.debug("Starting Unborn.py")

os.environ["DISPLAY"] = ":99"

# Load Google OAuth credentials from GitHub Secrets
CREDENTIALS_B64 = os.getenv("GOOGLE_OAUTH_CREDENTIALS_B64")
if not CREDENTIALS_B64:
    raise EnvironmentError("Google OAuth credentials not found in GitHub secrets!")

credentials_json = base64.b64decode(CREDENTIALS_B64).decode('utf-8')
credentials_dict = json.loads(credentials_json)

CREDENTIALS_PATH = 'credentials.json'
with open(CREDENTIALS_PATH, 'w') as f:
    json.dump(credentials_dict, f)

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
            logging.debug("Starting new OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')

    with open(TOKEN_PATH, 'w') as token:
        token.write(creds.to_json())

    return creds

# Set up Chrome WebDriver
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

service = Service("/usr/local/bin/chromedriver")
driver = webdriver.Chrome(service=service, options=chrome_options)
print("Chrome WebDriver successfully initialized!")

# Navigate to USDA LRP page
try:
    driver.set_page_load_timeout(180)
    driver.get("https://public.rma.usda.gov/livestockreports/LRPReport.aspx")
    WebDriverWait(driver, 60).until(lambda d: d.execute_script("return document.readyState") == "complete")
    time.sleep(5)  # Wait for ASP.NET JS to load dropdowns
except Exception as e:
    logging.error(f"Page load failed: {e}")
    driver.quit()
    exit(1)

# Dropdown selection function using partial ID
def select_dropdown_by_index_partial(id_fragment, index):
    try:
        print(f"Waiting for dropdown containing id: {id_fragment}")
        dropdown_element = WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located((By.XPATH, f"//select[contains(@id,'{id_fragment}')]"))
        )
        dropdown = Select(dropdown_element)
        dropdown.select_by_index(index)
        # Trigger change event for ASP.NET postback
        driver.execute_script("arguments[0].dispatchEvent(new Event('change'))", dropdown_element)
        time.sleep(2)
        print(f"Successfully selected index {index} from dropdown {id_fragment}")
        return True
    except Exception as e:
        print(f"Failed selecting dropdown {id_fragment}: {e}")
        return False

# Button click function
def click_button(button_id):
    try:
        button_element = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.ID, button_id))
        )
        button_element.click()
        WebDriverWait(driver, 30).until(lambda d: d.execute_script("return document.readyState") == "complete")
        time.sleep(2)
        print(f"Clicked button {button_id}")
        return True
    except Exception as e:
        print(f"Error clicking button {button_id}: {e}")
        return False

# Stop script if any step fails
def stop_if_failed(step):
    if not step:
        print("Critical error encountered! Stopping Script.")
        driver.quit()
        exit(1)

# Select dropdowns & click buttons in sequence
stop_if_failed(select_dropdown_by_index_partial("ddlEffectiveDt", 0))
stop_if_failed(click_button("_ctl0_cphContent_btnLRPNext"))

stop_if_failed(select_dropdown_by_index_partial("ddlLRPState", 33))
stop_if_failed(click_button("_ctl0_cphContent_btnLRPNext"))

stop_if_failed(select_dropdown_by_index_partial("ddlLRPCommodity", 1))
stop_if_failed(click_button("_ctl0_cphContent_btnLRPNext"))

stop_if_failed(select_dropdown_by_index_partial("ddlType", 9))
stop_if_failed(click_button("_ctl0_cphContent_btnCreateLRPReport"))

time.sleep(5)

# Extract table data
try:
    table = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.XPATH, "//table[@id='_ctl0_cphContent_tblContent']"))
    )
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
                    def format_price(price_text):
                        if not price_text.strip():
                            return "N/A"
                        match = re.search(r'(\$\d{1,6}(?:\.\d{0,2})?)', price_text)
                        return match.group() if match else price_text

                    selected_data.append([
                        cols[13].text if len(cols) > 13 else "N/A",
                        format_price(cols[8].text if len(cols) > 8 else "N/A"),
                        format_price(cols[12].text if len(cols) > 12 else "N/A")
                    ])
                    found_values[column_3_int] = True

    print(f"Selected Data: {selected_data}")

    # Send data to Google Sheets
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
