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
import re
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

service = build("sheets", "v4", credentials=get_google_sheets_service())

try:
	driver.get("https://public.rma.usda.gov/livestockreports/LRPReport.aspx")
	logging.debug("Page loaded successfully.")

	dropdown_element = driver.find_element(By.TAG_NAME, "select")
	logging.debug("Dropdown found.")

	select = Select(dropdown_element)
	first_option = select.options[0].text  # Extract only the first option
	logging.debug(f"Extracted first dropdown option: {first_option}")

	spreadsheet_id = '1eFn_RVcCw3MmdLRGASrYwoCbc1UPfFNVqq1Fbz2mvYg'
	range_name = 'Sheet1!D1'
	sheet = service.spreadsheets()

	update_values = [[first_option]]

	sheet.values().update(
		spreadsheetId=spreadsheet_id,
		range=range_name,
		valueInputOption="RAW",
		body={"values": update_values}
	).execute()

	print("First dropdown option successfully saved to Google Sheets!")

except Exception as e:
	print(f"Error extracting dropdown data: {e}")

finally:
	driver.quit()
	logging.debug("Script finished successfully")
