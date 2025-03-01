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

driver.get("https://public.rma.usda.gov/livestockreports/LRPReport.aspx")

dropdown_element = driver.find_element(By.TAG_NAME, "select")

select = Select(dropdown_element)
options = [option.text for option in select.options]

sheet_name = "Sheet1"
sheet = client.open_by_key(spreadsheet_id).worksheet(sheet_name)

# Upload dropdown options
sheet.update("D1", [["Dropdown Options"]] + [[option] for option in options])

print("First dropdown data successfully uploaded to Google Sheets!")

driver.quit()
logging.debug("Script finished successfully")
