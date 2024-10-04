import os
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.remote_connection import LOGGER
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options 
import praw
import schedule
import time

# Set logging level for Selenium to suppress output
LOGGER.setLevel(logging.WARNING)

# URL of the webpage
url = 'https://www.nexon.com/maplestory/news/all?page=1'
url_file = 'stored_urls.txt'

#get title of webpage
def get_title(url):
    # Create a new instance of the Chrome driver
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")  # Run in headless mode (without GUI)
    chrome_options.add_argument('--disable-gpu')  # Disable GPU hardware acceleration
    chrome_options.add_argument('--no-sandbox')  # Bypass OS security model
    chrome_options.add_argument('--window-size=1920x1080')  # Set window size
    chrome_options.add_argument('--ignore-certificate-errors')  # Ignore SSL certificate errors
    chrome_options.add_argument('--disable-dev-shm-usage')  # Overcome limited resource problems
    chrome_options.add_argument('--silent')  # Reduce logging

    service = Service('/usr/bin/chromedriver')
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        # Navigate to the desired webpage
        driver.get(url)
        with open('page_content.txt', 'w') as file:
            file.write(driver.page_source)

        # Wait for the title to be present (can be customized depending on page load behavior)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".news-detail__title.title.xs"))
        )

        # Wait for the title text to be non-empty
        title_element = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".news-detail__title.title.xs"))
        )

        # Get the text from the title element
        title = title_element.text

        # Wait a bit longer to ensure title is fully loaded (optional)
        WebDriverWait(driver, 10).until(lambda d: title_element.text != '')

        return title

    except Exception as e:
        print(f"An error occurred in get_title: {e}")

    finally:
        # Close the browser
        driver.quit()

if __name__ == "__main__":
   print(get_title("https://www.nexon.com/maplestory/news/"))
