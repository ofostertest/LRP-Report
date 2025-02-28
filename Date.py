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
from datetime import datetime
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
	creds = get_google_sheets_service()
	service = build('sheets', 'v4', credentials=creds)
	return service

def update_google_sheet(selected_data):
	service = get_sheets_service()
	spreadsheet_id = '1eFn_RVcCw3MmdLRGASrYwoCbc1UPfFNVqq1Fbz2mvYg'
	sheet_name = "Sheet1"
	range_name = 'Sheet1!C4'
	
	sheet = service.spreadsheets()
	
	update_values = selected_data
	sheet.values().update(
		spreadsheetId=spreadsheet_id,
		range=range_name,
		valueInputOption="RAW",
		body={"values": update_values}
	).execute()
	
	print("Data successfully saved to Google Sheets!")

	columns_to_watch = [3, 4, 5, 6, 7]
	range_to_check = f"{sheet_name}!C4:G58"
	
	result = service.spreadsheets().values().get(
		spreadsheetId=spreadsheet_id, 
		range=range_to_check
	).execute()

	data = result.get("values", [])
	
	changes_detected = any(any(row[i] for i in columns_to_watch) for row in data)
	if changes_detected:
		now = datetime.now().strftime("%m-%d-%Y")
		timestamp_range = f"{sheet_name}!D1"

		service.spreadsheets().values().update(
			spreadsheetId=spreadsheet_id,
			range=timestamp_range,
			valueInputOption="RAW",
			body={"values": [[now]]}
		).execute()
		
		print(f"Updated timestamp in D1: {now}")

try:
	selected_data = [["Row 1, Col 1", "Row 1, Col 2"], ["Row 2, Col 1", "Row 2, Col 2"]]

	update_google_sheet(selected_data)

except Exception as e:
	print(f"Error extracting table data: {e}")
		
logging.debug("Script finished successfully")
