from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os
import json
import base64
import time
import re
import logging

# ---------------------------------------------------
# Logging
# ---------------------------------------------------
logging.basicConfig(level=logging.DEBUG)
logging.debug("Starting LRP script")

os.environ["DISPLAY"] = ":99"

# ---------------------------------------------------
# Google OAuth
# ---------------------------------------------------
CREDENTIALS_B64 = os.getenv("GOOGLE_OAUTH_CREDENTIALS_B64")
if not CREDENTIALS_B64:
    raise EnvironmentError("Missing Google OAuth credentials")

credentials_json = base64.b64decode(CREDENTIALS_B64).decode("utf-8")
credentials_dict = json.loads(credentials_json)

with open("credentials.json", "w") as f:
    json.dump(credentials_dict, f)

TOKEN_PATH = "token.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def get_google_creds():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    return creds

# ---------------------------------------------------
# Selenium Setup
# ---------------------------------------------------
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")

driver = webdriver.Chrome(
    service=Service("/usr/local/bin/chromedriver"),
    options=chrome_options
)

print("Chrome WebDriver successfully initialized!")

# ---------------------------------------------------
# Helpers
# ---------------------------------------------------
def fatal(msg):
    logging.error(msg)
    driver.quit()
    exit(1)

def wait_for_options(select_id, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        count = driver.execute_script(
            f"return document.getElementById('{select_id}')?.options.length || 0;"
        )
        if count > 1:
            return True
        time.sleep(0.5)
    return False

def select_dropdown_js(select_id, index):
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, select_id))
        )

        if not wait_for_options(select_id):
            raise Exception("Options never loaded")

        driver.execute_script(f"""
            const sel = document.getElementById('{select_id}');
            sel.selectedIndex = {index};
            sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
        """)
        logging.debug(f"Selected {select_id} index {index}")
        time.sleep(1)
        return True

    except Exception as e:
        logging.error(f"Failed selecting dropdown {select_id}: {e}")
        return False

def click_next():
    try:
        btn = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//input[@type='submit' and @value='Next >>']")
            )
        )
        btn.click()
        time.sleep(2)
        return True
    except Exception as e:
        logging.error(f"Failed clicking Next >>: {e}")
        return False

# ---------------------------------------------------
# Load Page
# ---------------------------------------------------
driver.get("https://public.rma.usda.gov/livestockreports/LRPReport.aspx")

# ---------------------------------------------------
# Workflow
# ---------------------------------------------------
if not select_dropdown_js("EffectiveDate", 0):
    fatal("EffectiveDate failed")

if not click_next():
    fatal("Next failed")

if not select_dropdown_js("StateSelection", 33):
    fatal("StateSelection failed")

if not click_next():
    fatal("Next failed")

if not select_dropdown_js("CommoditySelection", 1):
    fatal("CommoditySelection failed")

if not click_next():
    fatal("Next failed")

if not select_dropdown_js("TypeSelection", 9):
    fatal("TypeSelection failed")

if not click_next():
    fatal("Final Next failed")

# ---------------------------------------------------
# Extract Table
# ---------------------------------------------------
try:
    report_div = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.ID, "oReportDiv"))
    )
    table = report_div.find_element(By.TAG_NAME, "table")
    rows = table.find_elements(By.TAG_NAME, "tr")

    target_values = {13, 17, 21, 26, 30, 34, 39, 43, 47}
    found = set()
    selected_data = []

    for row in rows:
        cols = row.find_elements(By.TAG_NAME, "td")
        if len(cols) < 14:
            continue

        val = cols[2].text.strip()
        if not val.isdigit():
            continue

        val = int(val)
        if val in target_values and val not in found:
            found.add(val)

            def price(txt):
                m = re.search(r"\$\d+(?:\.\d+)?", txt)
                return m.group(0) if m else "N/A"

            selected_data.append([
                cols[13].text,
                price(cols[8].text),
                price(cols[12].text)
            ])

    print("Selected Data:", selected_data)

except Exception as e:
    fatal(f"Table extraction failed: {e}")

# ---------------------------------------------------
# Google Sheets
# ---------------------------------------------------
creds = get_google_creds()
service = build("sheets", "v4", credentials=creds)

service.spreadsheets().values().update(
    spreadsheetId="1eFn_RVcCw3MmdLRGASrYwoCbc1UPfFNVqq1Fbz2mvYg",
    range="Sheet1!C4",
    valueInputOption="RAW",
    body={"values": selected_data}
).execute()

print("Data successfully saved to Google Sheets")

driver.quit()
logging.debug("Script finished successfully")
