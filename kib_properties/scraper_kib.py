""" this script scrapes villas and lands from a property website."""

import os
import time
import re
from dotenv import load_dotenv
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup


def upload_to_google(json_path, sheet_id, df):
    """ this function uploads data to a google sheet.

    It takes the service account credentials.json to make an object that
    connects with gspread to make a client.

    Then it saves the dataframe into the google sheet.

    """
    # Authenticate with Google Sheets using the JSON key file
    scope = ['https://www.googleapis.com/auth/spreadsheets',
             'https://www.googleapis.com/auth/drive']

    creds = Credentials.from_service_account_file(
        json_path, scopes=scope)

    client = gspread.authorize(creds)

    # Open the Google Sheet by id
    sheet = client.open_by_key(sheet_id)
    sheet1 = sheet.get_worksheet(0)

    # Convert the DataFrame to a list of lists
    data = df.values.tolist()

    # Clear existing data and update the Google Sheet with new data
    sheet1.clear()
    # Convert the DataFrame headers to a list and insert as the first row
    header_row = df.columns.tolist()
    sheet1.insert_rows([header_row], row=1)
    # insert the full data
    sheet1.insert_rows(data, row=2)


def obtain_links(base_url, website_page) -> list:
    """ This function returns a list of properties links that are displayed
    in a page.

    It takes the URL and the page number, and looks for the #box id element.
    Then it creates a beautiful soup element (soup) and scrapes the 'href'
    elements (links) that are inside the '.box.property-item' class.
    """
    # makes the url to be scraped, with the base url and the website page
    page_section = f"?page={website_page + 1}"
    url = base_url + page_section

    # go to url with Playwright page element
    page.goto(url)

    # tackle only the #box id
    html = page.inner_html('#box')

    # create beautiful soup element
    soup = BeautifulSoup(html, 'html.parser')

    # Find all elements with the class "box property-item"
    property_elements = soup.select('.box.property-item')

    # Extract the "href" attributes from the links
    property_links = [
        element.find('a')['href'] for element in property_elements]

    return property_links


def change_currency_n_get_soup(property_link) -> object:
    """ This function takes the property link and returns a beautiful soup
    element.

    At first it goes to link, then it clicks on the '.header-cur' class
    with the Playwright page method, it locates the text IDR  and clicks
    to change the currency. Finally it creates the soup element.

    """
    # go to new url provided by the link
    page.goto(property_link)

    # Click on the currency dropdown
    page.click('.header-cur')

    # then locate the currency IDR and click
    page.locator('text=IDR').first.click()

    # print to know that the currency was changed
    print('Currency changed!')

    html = page.inner_html('body')

    soup = BeautifulSoup(html, 'html.parser')

    return soup


def get_shared_features(soup):
    """ This function obtains the elements that are common for both villas and
    lands.

    It looks for several HTML classes and elements and returns:

    - colswidth20_item: a variable that is used later one
    - type_sale: the type of sale, lease or free
    - hold_years: the number of lease years
    - description_items: a list that is used later on to get more features.
    - date: the date of the upload, by using the image src

    """
    # get date using the image
    images = soup.select('figure')
    img_tags = images[0].find_all('img')
    img_src = img_tags[0].get('src')
    date = img_src.split('/')[-1].split('-property')[0]
    pattern = r"^\d{4}-\d{2}-\d{2}$"

    if not re.match(pattern, date):
        date = None

    # get elements inside colswidth20
    colswidth20_items = soup.select('.colswidth20')
    colswidth20_item = [
        colswidth20_item.text.strip()
        for colswidth20_item in colswidth20_items]

    # get sale type for each property
    type_sale = colswidth20_item[1] \
        .split('\n')[2].split(' ')[0]

    # get years if lease
    if type_sale == 'lease':
        hold_years = colswidth20_item[1] \
            .split('\n')[3].split('/ ')[1]
        hold_years = hold_years.split(' y')[0]
    else:
        hold_years = None

    # get items of property's description
    property_description = soup.select(
        '.property-description-row.flexbox')
    description_items = []

    # list items organized by "p" element
    for desc_row in property_description:
        items = desc_row.find_all('p')
        for paragraph in items:
            description_items.append(
                paragraph.text.strip())

    return type_sale, hold_years, description_items, colswidth20_item, date


def get_only_villas_features(soup, description_items, prices):
    """ This function returns only the elements that are specific for villas.
    They might be the same as the ones for lands, but the scraping process
    changes.

    It looks for several HTML classes and elements and returns:

    - rooms:  a list to get the bedrooms and bathrooms later
    - year_built: the year when the property was built
    - land_size: the size of the land
    - furnished: a string that shows if the property is fully, semi,
    or not furnished
    - pool: obtained from 'facilities' is just yes or no feature
    - price: the price of the villa

    """
    # get elements available (bedrooms and bathrooms)
    available_items = soup.select('.available')
    rooms = []
    for items in available_items:
        for paragraph in items:
            rooms.append(paragraph.text.strip())

    # if it findd the "Year Built" add it
    if 'Year Built' in description_items[5]:
        year_built = description_items[5]
        year_built = year_built.split(': ')[1]
        land_size = description_items[3]\
            .split('\n')[1].strip()
        building_size = description_items[6]\
            .split('\n')[1].strip()
        furnished = description_items[7]\
            .split('\n')[1].strip()
    else:
        year_built = None
        land_size = description_items[3]\
            .split('\n')[1].strip()
        building_size = description_items[5]\
            .split('\n')[1].strip()
        furnished = description_items[6]\
            .split('\n')[1].strip()

    # check for available facilities
    facilities = soup.select('.flexbox-wrap')
    facilities_available = []
    for facility in facilities:
        available_icons = facility.find_all('p')
        for icon in available_icons:
            if 'available' in str(icon):
                facilities_available.append(icon.text)

    if '\npoolPool' in facilities_available:
        pool = 'yes'
    else:
        pool = 'no'

    # clean price variable
    try:
        price = [price.text.strip().split(' ')[1]
                 .replace(',', '') for price in prices][0]
    except Exception as error:
        print(error)
        price = [price.text.strip() for price in prices][0]

    return price,\
        year_built, land_size, building_size, \
        pool, furnished, rooms


def get_only_lands_features(prices) -> str:
    """ This function returns only the elements that are specific for lands.
    They might be the same as the ones for villas, but the scraping process
    changes.

    It takes the 'prices' object and applies transformation to obtain the
    desired output, a string.

    """

    try:
        price = [price.text.strip().split('R ')[1]
                 .split('\n')[0]
                 .strip()
                 .replace(',', '') for price in prices][0]

    except Exception as error:
        print(error)
        price = [price.text.strip() for price in prices][0]

    return price


def scraper(url, n_pages=90) -> pd.DataFrame:
    """ This function takes all the other functions to build the scraping
    process.

    It starts by iterating over the website pages (n_pages), then it applies
    a function step by step until generating a dictionary for either villas
    or lands.

    Finally it creates a data frame for villas or lands and saves it as a .csv.
    """
    details = []

    for website_page in range(n_pages):
        print('page: ', website_page)
        property_links = obtain_links(url, website_page)
        for link in property_links:
            try:
                # make a beautiful soup object
                soup = change_currency_n_get_soup(link)

                # get the price of each property
                prices = soup.select('.regular-price')

                # get titles of each property
                titles = soup.select('.name')

                # get codes of each property
                codes = soup.select('.code')

            except Exception as error:
                print(error)
                time.sleep(60)
                continue

            try:
                type_sale, hold_years, description_items, colswidth20_item,\
                    date = get_shared_features(soup)

                if 'villas' in url:
                    price, year_built, land_size, building_size,\
                        pool, furnished, rooms = get_only_villas_features(
                            soup, description_items, prices)

                    detail = {
                        'Title': [
                            title.text.strip() for title in titles][0],
                        'Upload Date': date,
                        'Price (IDR)': price,
                        'Code': [
                            code.text.strip() for code in codes][0],
                        'Location': colswidth20_item[0].split('\n')[-1],
                        'Type of Sale': type_sale
                        .split(' ')[0],
                        'Lease Years': hold_years,
                        'URL': link,
                        'Property Type': 'villa',
                        'Year Built': year_built,
                        'Bedrooms': rooms[3].split('\n')[1],
                        'Bathrooms': rooms[5],
                        'Land Size (are)': land_size,
                        'Building Size (sqm)': building_size,
                        'Pool': pool,
                        'Furnished': furnished.lower()
                    }

                    details.append(detail)

                else:
                    price = get_only_lands_features(prices)

                    detail = {
                        'Title': [
                            title.text.strip() for title in titles][0],
                        'Upload Date': date,
                        'Price (IDR)': price,
                        'Code': [
                            code.text.strip() for code in codes][0],
                        'Location': colswidth20_item[0].split('\n')[-1],
                        'Type of Sale': type_sale
                        .split(' ')[0],
                        'Lease Years': hold_years,
                        'URL': link,
                        'Property Type': 'land',
                        'Year Built': None,
                        'Bedrooms': None,
                        'Bathrooms': None,
                        'Land Size (are)': description_items[3]
                        .split('\n')[1].strip(),
                        'Building Size (sqm)': None,
                        'Pool': None,
                        'Furnished': None
                    }

                    details.append(detail)

            except Exception as error:
                print(error)
            continue

    return pd.DataFrame(details)


if __name__ == '__main__':
    # path of the scraper
    PATH = os.path.dirname(__file__)

    # load environment keys
    load_dotenv(f"{PATH}/keys.env")

    # main URLs to be scraped
    URL_LANDS = os.getenv('URL_LANDS')
    URL_VILLAS = os.getenv('URL_VILLAS')

    # "with" statement for exception handling
    with sync_playwright() as p:
        # creates an instance of the Chromium browser and launches it
        browser = p.chromium.launch(headless=True)
        # creates a new browser page (tab) within the browser instance
        page = browser.new_page()

        try:
            # create lands dataframe
            df_lands = scraper(url=URL_LANDS, n_pages=4)
            # create villas dataframe
            df_villas = scraper(url=URL_VILLAS, n_pages=95)
            # merge both
            df_data = pd.concat([df_villas, df_lands])
            # save all datasets as .csv files
            df_lands.to_csv(f"{PATH}/data/lands.csv")
            df_villas.to_csv(f"{PATH}/data/villas_test.csv")
            df_data.to_csv(f"{PATH}/data/kib_data.csv")

        finally:
            page.close()

    upload merged dataframe to a google sheet
    upload_to_google(
        f"{PATH}/credentials.json",
        os.getenv('SHEET_ID'),
        df_data)
