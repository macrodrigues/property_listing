""" this script scrapes villas and lands from a property website."""

# pylint: disable=broad-except
import os
import time
import logging
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
    """ This function takes a new and a old dataset.

    It serves to trace the price changes on the platform.

    """
    if df_previous.empty:  # First-time scrape
        df['First Scrape Date'] = dt.datetime.now()\
            .strftime('%Y-%m-%d %H:%M:%S')
        df['Current Scrape Date'] = df['First Scrape Date']
        df['Original Price (USD)'] = df['Price (USD)']
        df['Original Price (IDR)'] = df['Price (IDR)']
    else:  # Subsequent scrapes
        logger.info("Old already exists")
        df['Current Scrape Date'] = dt.datetime.now()\
            .strftime('%Y-%m-%d %H:%M:%S')
        # Merge old and new data
        df_merged = pd.merge(
            df,
            df_previous[[
                'Code',
                'First Scrape Date',
                'Original Price (USD)',
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

    # Extract the "href" attributes from the links
    return [item.find('a')['href'] for item in
            soup.select('.box.property-item')]


def change_currency_n_get_soup(page, property_link,
                               currency='USD', idr_flag=0) -> object:
    """ This function takes the property link and returns a beautiful soup
    element.

    At first it goes to link, then it clicks on the '.header-cur' class
    with the Playwright page method, it locates the text IDR or USD and clicks
    to change the currency. Finally it creates the soup element.

    """
    # go to new url provided by the link
    page.goto(property_link)

    # Click on the currency dropdown
    page.click('.header-cur')

    # locate the currency IDR or USD and click
    if currency == 'USD':
        if idr_flag == 1:
            page.locator(f"text={currency}").nth(1).click()
        else:
            page.locator(f"text={currency}").nth(2).click()

    else:
        page.locator(f"text={currency}").nth(0).click()

    # print to know that the currency was changed
    # print(f"Currency changed to {currency}!")

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

    # get location
    location = colswidth20_item[0].split('\n')[-1]

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

    return type_sale, hold_years, description_items, date, location


def get_rooms_and_pool(soup):
    """ This function takes a Beautiful Soup Instance and scrapes content
    regarding the bedrooms, bathrooms and Pool.

    It is mainly used to avoid repetion in two functions that require
    these features.
    """
    # get bedrooms and bathrooms
    available_items = soup.select('.available')
    rooms = []
    for items in available_items:
        for paragraph in items:
            rooms.append(paragraph.text.strip())

    bedrooms = rooms[3].split('\n')[1]
    bathrooms = rooms[5]

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

    return bedrooms, bathrooms, pool


def get_only_villas_features(soup, description_items, prices, prices_usd):
    """ This function returns only the elements that are specific for villas.
    """

    # get bedrooms, bathrooms and pool
    bedrooms, bathrooms, pool = get_rooms_and_pool(soup)

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
            logger.error(error)
            furnished = None
            logger.info('furnished fixed!')

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
            logger.error(error)
            furnished = None
            logger.info('furnished fixed!')

    def get_price_parameters(prices):
        try:
            price = [price.text.strip() for price in prices][0]
            price = ''.join(re.findall(r'[\d.]+', price))
            price = float(price)
            payment_period = 'one time'
        except Exception as error:
            price = 0.0
            payment_period = 'on request'
            logger.error(str(error), ': FIXED!')

        return price, payment_period

    price_usd, payment_period_usd = get_price_parameters(prices_usd)
    price, payment_period = get_price_parameters(prices)

    return price, price_usd,\
        payment_period, payment_period_usd,\
        year_built, land_size, building_size, \
        pool, furnished, bedrooms, bathrooms


def get_only_villas_rents_features(soup, description_items):
    """ This function returns only the elements that are specific for
    villas rents.
    """

    # get bedrooms, bathrooms and pool
    bedrooms, bathrooms, pool = get_rooms_and_pool(soup)

    try:
        land_size = description_items[3]\
            .split('\n')[1].strip()
        building_size = description_items[4]\
            .split('\n')[1].strip()
    except Exception as error:
        building_size = description_items[5]\
            .split('\n')[1].strip()
        logger.error(str(error), ': FIXED')

    return land_size, building_size, pool, bedrooms, bathrooms


def get_renting_prices_periods(prices, prices_usd, property_type) -> str:
    """ This function returns only the elements that are specific for lands.
    They might be the same as the ones for villas, but the scraping process
    changes.

    It takes the 'prices' object and applies transformation to obtain the
    desired output, a string.

    """

    def get_price_parameters(prices, property_type):
        raw_string = [price.text.strip() for price in prices][0].strip()
        if property_type == 'villas':
            try:
                price_string = raw_string.split('/')[0]
                price = float(''.join(re.findall(r'[\d.]+', price_string)))
                if "\n" in raw_string:
                    payment_period = raw_string.split("\n")[1]\
                        .split('/')[1].strip()
                else:
                    payment_period = raw_string.split('/')[1].strip()
            except Exception as error:
                price = 0.0
                payment_period = 'on request'
                logger.error(str(error), ' :FIXED')
        else:
            try:
                if "\n" in raw_string:
                    price_string = raw_string.split("\n")[0]
                    if "/" in price_string:
                        price = float(
                            ''.join(re.findall(r'[\d.]+',
                                               price_string.split("/")[0])))
                        payment_period = price_string.split("/")[1]
                    else:
                        price = float(
                            ''.join(re.findall(r'[\d.]+', price_string)))
                        payment_period = 'one time'
                else:
                    if "/" in raw_string:
                        price = float(
                            ''.join(re.findall(r'[\d.]+',
                                               raw_string.split("/")[0])))
                        payment_period = raw_string.split("/")[1]
                    else:
                        price = float(
                            ''.join(re.findall(r'[\d.]+', raw_string)))
                        payment_period = 'one time'

            except Exception as error:
                price = 0.0
                payment_period = 'on request'
                logger.error(str(error), ' :FIXED')

        return price, payment_period

    price_usd, payment_period_usd = get_price_parameters(
        prices_usd,
        property_type)
    price, payment_period = get_price_parameters(
        prices,
        property_type)

    return price, price_usd, payment_period, payment_period_usd


def gen_detail_dict(
    title, date, price_usd, price, payment_period_usd, payment_period,
    code, location, type_sale, hold_years, link, property_type, year_built,
        bedrooms, bathrooms, land_size,
        building_size, pool, furnished) -> dict:
    """ This function returns a dictionary with all the information
    to be uploaded on the Google Sheets."""

    return {
        'Title': title,
        'Upload Date': date,
        'Price (USD)': price_usd,
        'Price (IDR)': price,
        'Payment Period (USD)': payment_period_usd,
        'Payment Period (IDR)': payment_period,
        'Code': code,
        'Location': location,
        'Type of Sale': type_sale,
        'Lease Years': hold_years,
        'URL': link,
        'Property Type': property_type,
        'Year Built': year_built,
        'Bedrooms': bedrooms,
        'Bathrooms': bathrooms,
        'Land Size (are)': land_size,
        'Building Size (sqm)': building_size,
        'Pool': pool,
        'Furnished': furnished
    }


def scraper(page, url, n_pages=90, flag=0) -> pd.DataFrame:
    """ This function takes all the other functions to build the scraping
    process.

    It starts by iterating over the website pages (n_pages), then it applies
    a function step by step until generating a dictionary for either villas
    or lands.

    Finally it creates a data frame for villas or lands and saves it as a .csv.
    """
    details = []
    for website_page in range(n_pages):
        logger.info(f"page: {website_page}")
        property_links = obtain_links(page, url, website_page)
        # add retries if it finds exception
        max_retries = 4
        for link in property_links:
            retries = 0
            while retries <= max_retries:
                try:
                    # make a beautiful soup object and convert to USD
                    soup_usd = change_currency_n_get_soup(
                        page, link, 'USD', flag)

                    # make a beautiful soup object and convert to IDR
                    soup = change_currency_n_get_soup(
                        page, link, 'IDR', flag)
                    flag = 1

                    # get the price of each property in IDR
                    prices_usd = soup_usd.select('.regular-price')

                    # get the price of each property in IDR
                    prices = soup.select('.regular-price')

                    # get titles of each property
                    titles = soup.select('.name')
                    title = [title.text.strip() for title in titles][0]

                    # get codes of each property
                    codes = soup.select('.code')
                    code = [code.text.strip() for code in codes][0]

                    type_sale, hold_years, description_items,\
                        date, location = get_shared_features(soup)

                    if 'villas-for-sale' in url:
                        price, price_usd, payment_period, payment_period_usd,\
                            year_built, land_size, building_size,\
                            pool, furnished, bedrooms,\
                            bathrooms = get_only_villas_features(
                                soup, description_items, prices, prices_usd)

                        detail = gen_detail_dict(
                            title, date, price_usd, price, payment_period_usd,
                            payment_period, code, location, type_sale,
                            hold_years, link, 'villa', year_built,
                            bedrooms, bathrooms,
                            land_size, building_size, pool, furnished)

                        details.append(detail)

                    if 'villas-for-rent' in url:
                        price, price_usd, payment_period, \
                            payment_period_usd = get_renting_prices_periods(
                                prices,
                                prices_usd,
                                'villas')

                        land_size, building_size,\
                            pool, bedrooms,\
                            bathrooms = get_only_villas_rents_features(
                                soup,
                                description_items)

                        detail = gen_detail_dict(
                            title, date, price_usd, price, payment_period_usd,
                            payment_period, code, location, None, None,
                            link, 'villa', None, bedrooms, bathrooms,
                            land_size, building_size, pool, None)

                        details.append(detail)

                    if 'land' in url:
                        price, price_usd, payment_period, \
                            payment_period_usd = get_renting_prices_periods(
                                prices,
                                prices_usd,
                                'lands')

                        land_size = description_items[3].split('\n')[1].strip()

                        detail = gen_detail_dict(
                            title, date, price_usd, price, payment_period_usd,
                            payment_period, code, location, type_sale,
                            hold_years, link, 'land', None, None, None,
                            land_size, None, None, None)

                        details.append(detail)

                    logger.info(f"{link}: PASS")
                    break

                except Exception as error:
                    logger.error(error)
                    logger.info(f"{link}: FAIL")
                    logger.info('retrying...')
                    retries += 1
                    time.sleep(5)

                if retries > max_retries:
                    logger.info("Max retries reached!")
                    continue

    return pd.DataFrame(details)


def main(url_lands, url_villas, url_villas_rents):
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
        num_villas_rents = get_last_page_number(page, url_villas_rents)

        try:
            # Authenticate Google Sheet and open the worksheet
            worksheet = google_authentication(
                f"{PATH}/credentials.json",
                os.getenv('SHEET_ID'))

            # Check for old data in the Google
            df_old = read_from_google(worksheet)

            # Scrape new data
            df_villas = scraper(
                page,
                url=URL_VILLAS,
                n_pages=num_villas-1,
                flag=0)  # flag parameter is used to adapt the currency click
            df_villas_rents = scraper(
                page,
                url=URL_VILLAS_RENTS,
                n_pages=num_villas_rents-1,
                flag=1)
            df_lands = scraper(
                page,
                url=URL_LANDS,
                n_pages=num_lands-1,
                flag=1)

            # Merge both
            df_new = pd.concat([df_villas, df_villas_rents, df_lands])

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

    # load environment keys
    load_dotenv(f"{PATH}/keys.env")

    # main URLs to be scraped
    URL_LANDS = os.getenv('URL_LANDS')
    URL_VILLAS = os.getenv('URL_VILLAS')
    URL_VILLAS_RENTS = os.getenv('URL_VILLAS_RENTS')

    # reorder columns
    column_order = [
        'Title',
        'Code',
        'Upload Date',
        'First Scrape Date',
        'Current Scrape Date',
        'Original Price (USD)',
        'Price (USD)',
        'Payment Period (USD)',
        'Original Price (IDR)',
        'Price (IDR)',
        'Payment Period (IDR)',
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

    # Create and configure logger
    logging.basicConfig(
        filename=f"app/scraper/logs/log_{dt.datetime.today()}.log",
        level=logging.NOTSET,
        format='%(asctime)s | %(levelname)s: %(message)s')
    logger = logging.getLogger()

    # run main function
    main(URL_LANDS, URL_VILLAS, URL_VILLAS_RENTS)
