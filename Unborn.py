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
import openpyxl
import os
import re
import gspread
import pandas as pd
import subprocess
import time
import logging
import base64
import json

logging.basicConfig(level=logging.DEBUG)
logging.debug("Starting Unborn.py")

logging.debug("Setting up ChromeDriver options")

os.environ["DISPLAY"] = ":99"

CREDENTIALS_B64 = os.getenv("GOOGLE_OAUTH_CREDENTIALS_B64")
if not CREDENTIALS_B64:
	raise EnvironmentError("Google OAuth credentials not found in GitHub secrets!")
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
	updated_token_b64 = base64.b64encode(creds.to_json().encode('utf-8')).decode('utf-8')

	print(f"Updated token: {updated_token_b64}")

	return creds

def get_sheets_service():
	creds = get_google_sheets_service()
	service = build('sheets', 'v4', credentials=creds)
	return service

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
	driver.set_page_load_timeout(180)  # Increase timeout to 3 minutes
	driver.get("https://public.rma.usda.gov/livestockreports/LRPReport.aspx")
except Exception as e:
	logging.error(f"Page load failed: {e}")
	driver.quit()
	exit(1)


def select_dropdown_by_index(dropdown_id, index):
	try:
		print(f"Waiting for dropdown: {dropdown_id}")
		dropdown_element = WebDriverWait(driver, 10).until(
			EC.presence_of_element_located((By.ID, dropdown_id))
		)
		print(f"Dropdown found: {dropdown_id}, attempting to select index {index}")
		
		dropdown = Select(dropdown_element)
		dropdown.select_by_index(index)
		time.sleep(1)
		print(f"Successfully selected index {index} from dropdown {dropdown_id}")
		return True

	except Exception as e:
		# Additional check to see if the element exists in the DOM at all
		try:
			raw_element = driver.find_element(By.ID, dropdown_id)
			print(f"Element exists but caused error: Tag={raw_element.tag_name}, Visible={raw_element.is_displayed()}")
		except:
			print(f"Dropdown element {dropdown_id} not found in DOM at all.")

		print(f"Error selecting dropdown {dropdown_id}: {e}")
		return False

def click_button(button_id):
	try:
		button_element = WebDriverWait(driver, 10).until(
			EC.element_to_be_clickable((By.ID, button_id))
		)
		button_element.click()
		time.sleep(2)
		print(f"Clicked button {button_id}")
		return True
	except Exception as e:
		print(f"Error clicking button {button_id}: {e}")
		return False

def stop_if_failed(step):
	if not step:
		print("Critical error encountered! Stopping Script.")
		driver.quit()
		exit(1)

stop_if_failed(select_dropdown_by_index("_ctl0_cphContent_ddlEffectiveDt", 0))
stop_if_failed(click_button("_ctl0_cphContent_btnLRPNext"))

stop_if_failed(select_dropdown_by_index("_ctl0_cphContent_ddlLRPState", 33))
stop_if_failed(click_button("_ctl0_cphContent_btnLRPNext"))

stop_if_failed(select_dropdown_by_index("_ctl0_cphContent_ddlLRPCommodity", 1))
stop_if_failed(click_button("_ctl0_cphContent_btnLRPNext"))

stop_if_failed(select_dropdown_by_index("_ctl0_cphContent_ddlType", 9))
stop_if_failed(click_button("_ctl0_cphContent_btnCreateLRPReport"))

time.sleep(5)

file_path = 'LRP-Spreadsheet.xlsx'

body = driver.find_element(By.TAG_NAME, 'body')

try:
	table = WebDriverWait(driver, 20).until(
		EC.presence_of_element_located((By.XPATH, "//table[@id='_ctl0_cphContent_tblContent']"))
	)
	WebDriverWait(driver, 10).until(
		EC.presence_of_element_located((By.XPATH, "//table[@id='_ctl0_cphContent_tblContent']/tbody/tr[last()]"))
	)
	time.sleep(3)
	
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
						cols[13].text if len (cols) > 13 else "N/A",
						formatted_price_8,
						formatted_price_12
					])

					found_values[column_3_int] = True

	print(f"Selected Data: {selected_data}")

	service = build("sheets", "v4", credentials=get_google_sheets_service())

	spreadsheet_id = '1eFn_RVcCw3MmdLRGASrYwoCbc1UPfFNVqq1Fbz2mvYg'
	range_name = 'Sheet1!C4'
	sheet = service.spreadsheets()
	update_values = selected_data
	request = sheet.values().update(spreadsheetId=spreadsheet_id,range=range_name,valueInputOption="RAW",body={"values": update_values}).execute()

	print("Data successfully saved to Google Sheets!")

except Exception as e:
	print(f"Error extracting table data: {e}")

driver.quit()
logging.debug("Script finished successfully")
