import os
from dotenv import load_dotenv
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.remote_connection import LOGGER
from webdriver_manager.chrome import ChromeDriverManager
import praw
import schedule
import time
from bs4 import BeautifulSoup

# Load environment variables from .env file
load_dotenv()

# Reddit credentials from environment variables
reddit_username = os.getenv('REDDIT_USERNAME')
reddit_password = os.getenv('REDDIT_PASSWORD')
reddit_client_id = os.getenv('REDDIT_CLIENT_ID')
reddit_client_secret = os.getenv('REDDIT_CLIENT_SECRET')
reddit_user_agent = os.getenv('REDDIT_USER_AGENT')
reddit_subreddit = ('hxydn')

def get_first_news_link(url):
    # Create a new instance of the Chrome driver with headless options
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--window-size=1920x1080')
    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_argument('--disable-dev-shm-usage')

    service = Service('/usr/bin/chromedriver')
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        # Navigate to the URL
        driver.get(url)

        # Get the page source
        page_source = driver.page_source

        # Use BeautifulSoup to parse the HTML
        soup = BeautifulSoup(page_source, 'html.parser')

        # Find the first anchor tag with href containing "/maplestory/news/"
        first_news_link = None
        for a_tag in soup.find_all('a', href=True):
            if "/maplestory/news/" in a_tag['href']:
                first_news_link = "https://www.nexon.com" + a_tag['href']
                break  # Stop after finding the first instance

        # If we found a link, check if it is new
        if first_news_link:
            # Check if news.txt exists
            if os.path.exists('news.txt'):
                # Read the existing URL from the file
                with open('news.txt', 'r') as file:
                    existing_url = file.read().strip()

                # Compare with the new URL
                if existing_url == first_news_link:
                    print("No new post")
                    return None
                else:
                    # If different, update the file and return the new URL
                    with open('news.txt', 'w') as file:
                        file.write(first_news_link)
                    print(f"New post found: {first_news_link}")
                    return first_news_link
            else:
                # If file doesn't exist, create it and save the new URL
                with open('news.txt', 'w') as file:
                    file.write(first_news_link)
                print(f"New post found: {first_news_link}")
                return first_news_link
        else:
            print("No news links found.")
            return None

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
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

    service = Service('/usr/bin/chromedriver')
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
def post_to_reddit(url,name):
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
            title=name, 
            url=url)
        print(f"Posted to r/{reddit_subreddit}: {submission.title} - {submission.url}")
    except Exception as e:
        print(f"An error occurred while posting to Reddit: {e}")

if __name__ == "__main__":
    link = get_first_news_link("https://www.nexon.com/maplestory/news/all?page=1")
    if link:
        name = get_title(link)
        post_to_reddit(link,name)
    else:
        print("end task")
