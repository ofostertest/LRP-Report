service = build("sheets", "v4", credentials=get_google_sheets_service())
        
	spreadsheet_id = '1eFn_RVcCw3MmdLRGASrYwoCbc1UPfFNVqq1Fbz2mvYg'
	sheet_name = "Sheet1"
	range_name = 'Sheet1!C4'
	
	sheet = service.spreadsheets()
	
	update_values = selected_data
	request = sheet.values().update(spreadsheetId=spreadsheet_id,range=range_name,valueInputOption="RAW",body={"values": update_values}).execute()
	
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

except Exception as e:
	print(f"Error extracting table data: {e}")

driver.quit()
logging.debug("Script finished successfully")
