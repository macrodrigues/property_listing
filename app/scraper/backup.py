import os
from google_access import copy_spreadsheet
from dotenv import load_dotenv

# path of the scraper
PATH = os.path.dirname(os.path.dirname(__file__))

if __name__ == "__main__":
    # load environment keys
    load_dotenv(f"{PATH}/keys.env")

    # copy spreadsheet
    copy_spreadsheet(
        f"{PATH}/credentials.json",
        sheet_id_to_copy=os.getenv('SHEET_ID'))
