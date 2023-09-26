""" Script containing the Google interaction functions.

One for authentication, one for reading and one for uploading.

"""
import pandas as pd
import datetime as dt
import gspread
from google.oauth2.service_account import Credentials


def google_authentication(credentials, sheet_id) -> object:
    """ This function gives authentication to the Google Account.

    Scopes defines the permissions to Googe Sheets and Google Drive.
    Than, using gspread, it authorizes the authentication and
    opens the the worksheet to work with.

    """
    # Authenticate with Google Sheets using the JSON key file
    scope = ['https://www.googleapis.com/auth/spreadsheets',
             'https://www.googleapis.com/auth/drive']

    creds = Credentials.from_service_account_file(
        credentials, scopes=scope)

    client = gspread.authorize(creds)

    # Open the Google Sheet by id
    sheet = client.open_by_key(sheet_id)
    work_sheet = sheet.get_worksheet(0)
    return work_sheet


def read_from_google(sheet) -> pd.DataFrame:
    """ This function reads the data from the Google Sheet. """
    df_previous = pd.DataFrame(data=sheet.get_all_records())
    return df_previous


def upload_to_google(df, sheet):
    """ This function uploads the data to a google sheet.

    It takes the worksheet object created in google_authentication(), and
    writes data from a dataframe to it.

    """

    # Convert the DataFrame to a list of lists
    data = df.values.tolist()

    # Clear existing data and update the Google Sheet with new data
    sheet.clear()

    # Convert the DataFrame headers to a list and insert as the first row
    header_row = df.columns.tolist()
    sheet.insert_rows([header_row], row=1)

    # insert the full data
    sheet.insert_rows(data, row=2)


def copy_spreadsheet(credentials, sheet_id_to_copy):
    """ This function makes a Google authentication, then
    it takes a sheet_id and copies to the Archives folder """

    # Authenticate with Google Sheets using the JSON key file
    scope = ['https://www.googleapis.com/auth/spreadsheets',
             "https://www.googleapis.com/auth/drive"]

    creds = Credentials.from_service_account_file(
        credentials, scopes=scope)

    client = gspread.authorize(creds)

    client.copy(
        sheet_id_to_copy,
        title=f"Backup {str(dt.date.today())}",
        copy_permissions=True,
        folder_id='1MX2UbskY-PU_4d0GdkN8FcU9yu0RiBNE')
