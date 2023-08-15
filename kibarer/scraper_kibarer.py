""" this script scrapes villas and lands from Kibarer property website."""

import time
import pandas as pd
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup


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

    """
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

    return type_sale, hold_years, description_items, colswidth20_item


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
        price = float(
            [price.text.strip().split(' ')[1]
                .replace(',', '') for price in prices][0])
    except Exception.with_traceback() as error:
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

    except Exception.with_traceback() as error:
        print(error)
        price = [price.text.strip() for price in prices][0]

    return price


def scrape_kibarer(url, n_pages=90):
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

            except Exception.with_traceback() as error:
                print(error)
                time.sleep(60)
                continue

            try:
                type_sale, hold_years, description_items, colswidth20_item\
                    = get_shared_features(soup)

                if 'villas' in url:
                    price, year_built, land_size, building_size,\
                        pool, furnished, rooms = get_only_villas_features(
                            soup, description_items, prices)

                    detail = {
                        'Title': [
                            title.text.strip() for title in titles][0],
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

            except Exception.with_traceback() as error:
                print(error)
            continue

    df_res = pd.DataFrame(details)
    if 'villas' in url:
        df_res.to_csv('villas.csv')
    else:
        df_res.to_csv('lands.csv')


if __name__ == '__main__':
    URL_LANDS = 'https://www.villabalisale.com/search/land'
    URL_VILLAS = 'https://www.villabalisale.com/search/villas-for-sale'

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            scrape_kibarer(url=URL_VILLAS, n_pages=4)
        finally:
            page.close()
