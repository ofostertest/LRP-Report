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
	credentials_json = base64.b64decode(os.getenv("GOOGLE_OAUTH_CREDENTIALS_B64")).decode('utf-8')
	credentials_dict = json.loads(credentials_json)

	creds = Credentials(
		None,
		refresh_token=os.getenv("GOOGLE_REFRESH_TOKEN"),
		token_uri=credentials_dict['installed']['token_uri'],
		client_id=credentials_dict['installed']['client_id'],
		client_secret=credentials_dict['installed']['client_secret'],
		scopes=SCOPES
	)

	creds.refresh(Request())
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
