""" this script scrapes villas and lands from a property website."""

# pylint: disable=broad-except
import os
import time
import re
import datetime as dt
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from google_access import pd, google_authentication
from google_access import upload_to_google, read_from_google
from bs4 import BeautifulSoup


def get_last_page_number(page, url) -> int:
    """This function looks for the last page to scrape.

    By looking for the pagination id, it finds the page-item elements.
    These are converted to a list, then the function takes the
    last number shown on the pagination.

    """
    # go to url with Playwright page element
    page.goto(url)

    # tackle only the #box id
    html = page.inner_html('#pagination')

    # create beautiful soup element
    soup = BeautifulSoup(html, 'html.parser')

    # Find all elements with the class "box property-item"
    page_items = soup.find_all('li', {'class': 'page-item'})

    return int(page_items[-2].text)


def update_dataframe(df, df_previous) -> pd.DataFrame:
    """ This function it takes a new and a old dataset.

    It serves to trace the price changes on the platform.

    """
    if df_previous.empty:  # First-time scrape
        df['First Scrape Date'] = dt.datetime.now()\
            .strftime('%Y-%m-%d %H:%M:%S')
        df['Current Scrape Date'] = df['First Scrape Date']
        df['Original Price (USD)'] = df['Price (USD)']
        df['Original Price (IDR)'] = df['Price (IDR)']
    else:  # Subsequent scrapes
        print("Old already exists")
        df['Current Scrape Date'] = dt.datetime.now()\
            .strftime('%Y-%m-%d %H:%M:%S')
        # Merge old and new data
        df_merged = pd.merge(
            df,
            df_previous[[
                'Code',
                'First Scrape Date',
                'Original Price (USD)'
                'Original Price (IDR)']], on='Code', how='left')

        df = df_merged

    return df


def obtain_links(page, base_url, website_page) -> list:
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


def change_currency_n_get_soup(page, property_link) -> object:
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
    img_src = soup.select('figure')[0].find_all('img')[0].get('src')
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
        .split('\n')[2].split(' ')[0] + "hold"

    # get years if lease
    if type_sale == 'leasehold':
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


def get_only_villas_features(soup, description_items, prices, prices_usd):
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

    # if it finds the "Year Built" add it
    if 'Year Built' in description_items[5]:
        year_built = description_items[5]
        year_built = year_built.split(': ')[1]
        land_size = description_items[3]\
            .split('\n')[1].strip()
        building_size = description_items[6]\
            .split('\n')[1].strip()
        try:
            furnished = description_items[7]\
                .split('\n')[1].strip().lower()
        except Exception as error:
            print(error)
            furnished = None
            print('furnished fixed!')

    else:
        year_built = None
        land_size = description_items[3]\
            .split('\n')[1].strip()
        building_size = description_items[5]\
            .split('\n')[1].strip()
        try:
            furnished = description_items[6]\
                .split('\n')[1].strip()
        except Exception as error:
            print(error)
            furnished = None
            print('furnished fixed!')

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
        price_usd = [price_usd.text.strip().split(' ')[1]
                     .replace(',', '') for price_usd in prices_usd][0]
        price = [price.text.strip().split(' ')[1]
                 .replace(',', '') for price in prices][0]
    except Exception as error:
        print(error)
        price = [price.text.strip() for price in prices][0]
        price_usd = [price_usd.text.strip() for price_usd in prices_usd][0]

    return price, price_usd,\
        year_built, land_size, building_size, \
        pool, furnished, rooms


def get_only_lands_features(prices, prices_usd) -> str:
    """ This function returns only the elements that are specific for lands.
    They might be the same as the ones for villas, but the scraping process
    changes.

    It takes the 'prices' object and applies transformation to obtain the
    desired output, a string.

    """

    try:
        price = [price.text.strip().split(' ')[1]
                 .split('\n')[0]
                 .strip()
                 .replace(',', '') for price in prices][0]
        price_usd = [price_usd.text.strip().split(' ')[1]
                     .split('\n')[0]
                     .strip()
                     .replace(',', '') for price_usd in prices_usd][0]

    except Exception as error:
        print(error)
        price = [price.text.strip() for price in prices][0]
        price_usd = [price_usd.text.strip() for price_usd in prices_usd][0]

    return price, price_usd


def scraper(page, url, n_pages=90) -> pd.DataFrame:
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
        property_links = obtain_links(page, url, website_page)
        for link in property_links:
            try:
                # go to new url provided by the link
                page.goto(link)

                html = page.inner_html('body')

                soup = BeautifulSoup(html, 'html.parser')

                # get prices in usd
                prices_usd = soup.select('.regular-price')

                # make a beautiful soup object
                soup = change_currency_n_get_soup(page, link)

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
                    price, price_usd, year_built, land_size, building_size,\
                        pool, furnished, rooms = get_only_villas_features(
                            soup, description_items, prices, prices_usd)

                    detail = {
                        'Title': [
                            title.text.strip() for title in titles][0],
                        'Upload Date': date,
                        'Price (USD)': price_usd,
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
                        'Furnished': furnished
                    }

                    details.append(detail)

                else:
                    price, price_usd = get_only_lands_features(
                        prices,
                        prices_usd)

                    detail = {
                        'Title': [
                            title.text.strip() for title in titles][0],
                        'Upload Date': date,
                        'Price (USD)': price_usd,
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
                print(link)
            continue

    return pd.DataFrame(details)


def main(url_lands, url_villas):
    """ Main function """
    # "with" statement for exception handling
    with sync_playwright() as pw:
        # creates an instance of the Chromium browser and launches it
        browser = pw.chromium.launch(headless=True)
        # creates a new browser page (tab) within the browser instance
        page = browser.new_page()

        # Get last page to iterate
        num_lands = get_last_page_number(page, url_lands)
        num_villas = get_last_page_number(page, url_villas)

        try:
            # Authenticate Google Sheet and open the worksheet
            worksheet = google_authentication(
                f"{PATH}/credentials.json",
                os.getenv('SHEET_ID'))

            # Check for old data in the Google
            df_old = read_from_google(worksheet)

            # Scrape new data
            df_lands = scraper(
                page,
                url=URL_LANDS,
                n_pages=num_lands-1)
            df_villas = scraper(
                page,
                url=URL_VILLAS,
                n_pages=num_villas-num_villas)

            # Merge both
            df_new = pd.concat([df_villas, df_lands])

            # Update dataframe
            df_new = update_dataframe(df_new, df_old)

            # apply reorder
            df_new = df_new[column_order]

            # Upload to Google Sheet with new information
            upload_to_google(df_new, worksheet)

        finally:
            page.close()


if __name__ == '__main__':
    # path of the scraper
    PATH = os.path.dirname(os.path.dirname(__file__))

    print(PATH)

    # load environment keys
    load_dotenv(f"{PATH}/keys.env")

    # main URLs to be scraped
    URL_LANDS = os.getenv('URL_LANDS')
    URL_VILLAS = os.getenv('URL_VILLAS')

    # reorder columns
    column_order = [
        'Title',
        'Code',
        'Upload Date',
        'First Scrape Date',
        'Current Scrape Date',
        'Original Price (USD)',
        'Price (USD)',
        'Original Price (IDR)',
        'Price (IDR)',
        'Location',
        'Type of Sale',
        'Lease Years',
        'URL',
        'Property Type',
        'Year Built',
        'Bedrooms',
        'Bathrooms',
        'Land Size (are)',
        'Building Size (sqm)',
        'Pool',
        'Furnished']

    # run main function
    main(URL_LANDS, URL_VILLAS)
