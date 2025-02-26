from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import openpyxl
import os
import gspread
import pandas as pd
import time
import logging

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

CREDENTIALS_PATH = 'credentials.json'
TOKEN_PATH = 'token.json'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def get_google_sheets_service():
	creds = None
	if os.path.exists(TOKEN_PATH):
		creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
	if not creds or not creds.valid:
		if creds and creds.expired and creds.refresh_token:
			creds.refresh(Request())
		else:
			flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
			creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')
		with open(TOKEN_PATH, "w") as token:
			token.write(creds.to_json())
	return creds

def get_sheets_service():
	creds = authenticate_google_sheets()
	service = build('sheets', 'v4', credentials=creds)
	return service

logging.basicConfig(level=logging.DEBUG)
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

driver.get("https://public.rma.usda.gov/livestockreports/LRPReport.aspx")

def select_dropdown_by_index(dropdown_id, index):
	try:
		dropdown_element = WebDriverWait(driver,10).until(
			EC.presence_of_element_located((By.ID, dropdown_id))
		)
		dropdown = Select(dropdown_element)
		dropdown.select_by_index(index)
		time.sleep(1)
		print(f"Selected index {index} from dropdown {dropdown_id}")
	except Exception as e:
		print(f"Error selecting dropdown {dropdown_id}: {e}")

def click_button(button_id):
	try:
		button_element = WebDriverWait(driver, 10).until(
			EC.element_to_be_clickable((By.ID, button_id))
		)
		button_element.click()
		time.sleep(2)
		print(f"Clicked button {button_id}")
	except Exception as e:
		print(f"Error clicking button {button_id}: {e}")

select_dropdown_by_index("_ctl0_cphContent_ddlEffectiveDt", 0)
click_button("_ctl0_cphContent_btnLRPNext")

select_dropdown_by_index("_ctl0_cphContent_ddlLRPState", 33)
click_button("_ctl0_cphContent_btnLRPNext")

select_dropdown_by_index("_ctl0_cphContent_ddlLRPCommodity", 1)
click_button("_ctl0_cphContent_btnLRPNext")

select_dropdown_by_index("_ctl0_cphContent_ddlType", 1)
click_button("_ctl0_cphContent_btnCreateLRPReport")

time.sleep(5)

file_path = 'LRP-Spreadsheet.xlsx'

body = driver.find_element(By.TAG_NAME, 'body')

try:
	table = WebDriverWait(driver,20).until(
		EC.presence_of_element_located((By.XPATH, "//table[@id='_ctl0_cphContent_tblContent']"))
	)
	rows = table.find_elements(By.TAG_NAME,"tr")

	selected_rows = [7, 19, 31, 43, 55, 67, 86, 98, 110]
	selected_data = []

	for i, row in enumerate(rows,start=1):
		if i in selected_rows:
			cols = row.find_elements(By.TAG_NAME,"td")
			if len(cols)>13:
				selected_data.append([
					cols[13].text,
					cols[8].text,
					cols[12].text
				])
	print(f"Selected Data: {selected_data}")

	service = build("sheets","v4", credentials=get_google_sheets_service())
	
	spreadsheet_id = '1eFn_RVcCw3MmdLRGASrYwoCbc1UPfFNVqq1Fbz2mvYg'
	range_name = 'Sheet1!C15'
	sheet = service.spreadsheets()
	update_values = selected_data
	request = sheet.values().update(spreadsheetId=spreadsheet_id,range=range_name,valueInputOption="RAW",body={"values": update_values}).execute()
	
	print("Data successfully saved to Google Sheets!") 

except Exception as e:
	print(f"Error extracting table data: {e}")

driver.quit()
