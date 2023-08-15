from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)  # Launch headless browser
    page = browser.new_page()  # Open a new tab

    url = 'https://www.villabalisale.com/search/villas-for-sale'

    try:
        page.goto(url)

        # count pages
        counter = 2

        # Use CSS selector to extract details
        details = []

        # number of pages

        paginations = 8

        for pagination in range(paginations):

            print(pagination)

            html = page.inner_html('#box')
            soup = BeautifulSoup(html, 'html.parser')

            # Find all elements with the class "box property-item"
            property_elements = soup.select('.box.property-item')

            # Extract the "href" attributes from the links
            property_links = [
                element.find('a')['href'] for element in property_elements]

            for link in property_links:
                page.goto(link)

                # Click on the currency dropdown
                page.click('.header-cur')

                # then locate the currency IDR and click
                page.locator('text=IDR').first.click()

                print('Currency changed!')

                html = page.inner_html('body')

                soup = BeautifulSoup(html, 'html.parser')

                # get the price of each property
                prices = soup.select('.regular-price')

                # get titles of each property
                titles = soup.select('.name')

                # get codes of each property
                codes = soup.select('.code')

                try:
                    # get elements inside colswidth20
                    colswidth20_items = soup.select('.colswidth20')
                    colswidth20_item = [
                        colswidth20_item.text.strip()
                        for colswidth20_item in colswidth20_items]

                    # get elements inside available (bedrooms and bathrooms)
                    available_items = soup.select('.available')
                    rooms = []
                    for items in available_items:
                        for paragraph in items:
                            rooms.append(paragraph.text.strip())

                    # get sale type for each property
                    type_sale = colswidth20_item[1] \
                        .split('\n')[2].split(' ')[0]

                    # get years if lease
                    if type_sale == 'lease':
                        hold_years = colswidth20_item[1] \
                            .split('\n')[3].split('/ ')[1]
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
                            description_items.append(paragraph.text.strip())

                    # if it findd the "Year Built" add it
                    if 'Year Built' in description_items[5]:
                        year_built = description_items[5]
                        land_size = description_items[3].split('\n')[1].strip()
                        building_size = description_items[6]\
                            .split('\n')[1].strip()
                        furnished = description_items[7].split('\n')[1].strip()
                    else:
                        year_built = None
                        land_size = description_items[3].split('\n')[1].strip()
                        building_size = description_items[5]\
                            .split('\n')[1].strip()
                        furnished = description_items[6].split('\n')[1].strip()

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

                    detail = {
                        'Title': [title.text.strip() for title in titles][0],
                        'Price': [price.text.strip() for price in prices][0],
                        'Code': [code.text.strip() for code in codes][0],
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

                except Exception as e:
                    print(e)
                    continue

            # increase page
            pagination += 1

            # go back to the main url
            page.goto(url)

            # Locate and click on the .page-link element with specific text
            page_links = page.locator('.page-link').all()
            page_links[pagination + 1].click()

            # Wait for the page to load
            page.wait_for_timeout(10000)
            page.wait_for_load_state('domcontentloaded', timeout=10000)

            page.screenshot(path="screenshot.png")

        df = pd.DataFrame(details)
        df.to_csv('villas.csv')

    finally:
        page.close()
