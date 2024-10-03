import os
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.remote_connection import LOGGER
from webdriver_manager.chrome import ChromeDriverManager
import praw
import schedule
import time

# Set logging level for Selenium to suppress output
LOGGER.setLevel(logging.WARNING)

# URL of the webpage
url = 'https://www.nexon.com/maplestory/news/all?page=1'
url_file = 'stored_urls.txt'

# Reddit credentials
reddit_username = 
reddit_password = 
reddit_client_id = 
reddit_client_secret = 
reddit_user_agent = 
reddit_subreddit = 'hxydn'

def get_child_hrefs():
    # Set up Chrome options
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")  # Run in headless mode (without GUI)
    chrome_options.add_argument('--disable-gpu')  # Disable GPU hardware acceleration
    chrome_options.add_argument('--no-sandbox')  # Bypass OS security model
    chrome_options.add_argument('--window-size=1920x1080')  # Set window size
    chrome_options.add_argument('--ignore-certificate-errors')  # Ignore SSL certificate errors
    chrome_options.add_argument('--disable-dev-shm-usage')  # Overcome limited resource problems
    chrome_options.add_argument('--log-level=3')  # Suppress ChromeDriver logs
    chrome_options.add_argument('--silent')  # Additional silent mode

    # Initialize the Chrome WebDriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        # Open the specified URL
        driver.get(url)
        print("Page loaded.")

        # Wait for the pagination items to be present
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.pagination__list-items a'))
        )
        
        items = driver.find_elements(By.CSS_SELECTOR, '.pagination__list-items a')
        
        if not items:
            print("No pagination list items found.")
            return None
        
        # Get the href of the first child <a> tag
        first_href = items[0].get_attribute('href')
        print(f"First Href: {first_href}")

        # Read the existing URLs from the file if it exists
        if os.path.exists(url_file):
            with open(url_file, 'r') as file:
                stored_hrefs = file.read().strip().split(',')
                stored_hrefs = [href.strip() for href in stored_hrefs]  # Clean whitespace
        else:
            stored_hrefs = []

        # Debug outputs
        print("Stored Hrefs:", stored_hrefs)
        
        # Check for changes
        if stored_hrefs and stored_hrefs[0] == first_href:
            print("The first URL is unchanged.")
            return None
        
        # Store the new URLs in the file
        with open(url_file, 'w') as file:
            file.write(first_href)
        print("Updated the stored URLs.")

        return first_href  # Return the first href to post to Reddit

    except Exception as e:
        print(f"An error occurred in get_child_hrefs: {e}")
    
    finally:
        # Close the WebDriver
        driver.quit()

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

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        # Navigate to the desired webpage
        driver.get(url)

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

# Function to post to Reddit
def post_to_reddit(url):
    reddit = praw.Reddit(
        client_id=reddit_client_id,
        client_secret=reddit_client_secret,
        user_agent=reddit_user_agent,
        username=reddit_username,
        password=reddit_password
    )
    print("logged in")

    try:
        title = get_title(url)
        subreddit = reddit.subreddit(reddit_subreddit)
        submission = subreddit.submit(
            title=title, 
            url=url)
        print(f"Posted to r/{reddit_subreddit}: {submission.title} - {submission.url}")
    except Exception as e:
        print(f"An error occurred while posting to Reddit: {e}")


def task():
    print("running task")
    first_href = get_child_hrefs()
    if first_href:
        post_to_reddit(first_href)
    else:
        print("no new post")

if __name__ == "__main__":
    # Schedule the task to run at xx:00 and xx:30 every hour
    print("booting up")
    schedule.every().hour.at(":05").do(task)
    schedule.every().hour.at(":35").do(task)

    # Run the scheduler loop forever
    while True:
        schedule.run_pending()
        time.sleep(1)