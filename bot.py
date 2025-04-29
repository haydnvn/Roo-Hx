import os
import re
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
reddit_subreddit = ('maplestory')

def get_first_news_link(url, skip_links=[]):
    # Load previously posted links from news.txt
    posted_links = set()
    if os.path.exists('news.txt'):
        with open('news.txt', 'r') as file:
            posted_links = set(line.strip() for line in file.readlines())

    # Create a new instance of the Chrome driver
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

        # Find all anchor tags with href containing "/maplestory/news/"
        news_links = [
            "https://www.nexon.com" + a_tag['href']
            for a_tag in soup.find_all('a', href=True)
            if "/maplestory/news/" in a_tag['href']
        ]

        # Check only the first three links
        first_three_links = news_links[:3]
        print(first_three_links)
        # Filter out links already posted or skipped
        filtered_links = [
            link for link in first_three_links
            if link not in posted_links and link not in skip_links
        ]

        # Return the first non-skipped and non-posted link
        if filtered_links:
            first_news_link = filtered_links[0]

            # Append the link to news.txt
            with open('news.txt', 'a') as file:
                file.write(first_news_link + '\n')

            print(f"New post found: {first_news_link}")
            return first_news_link
        else:
            print("No new news links found in the first three links.")
            return None

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        driver.quit()



def parse_url_title(url):
    # Regex pattern to match URLs with the specified format
    pattern = r"https://www\.nexon\.com/maplestory/news/\w+/\d{5}/([\w-]+)"
    
    # Search for the pattern in the URL
    match = re.search(pattern, url)
    
    if match:
        # Extract the title part and replace dashes with spaces, then capitalize each word
        title = match.group(1).replace('-', ' ')
        return title.title()  # Capitalize the first letter of each word
    
    return None  # Return None if URL doesn't match the pattern

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
        if(title is None):
            title = parse_url_title(url)
        return title

    except Exception as e:
        print(f"An error occurred in get_title: {e}")

    finally:
        # Close the browser
        driver.quit()





def post_to_reddit(url, name):
    reddit = praw.Reddit(
        client_id=reddit_client_id,
        client_secret=reddit_client_secret,
        user_agent=reddit_user_agent,
        username=reddit_username,
        password=reddit_password
    )
    print("Logged in")

    try:
        # Get the title and subreddit
        title = name
        subreddit = reddit.subreddit(reddit_subreddit)
        
        # Set the "Information" flair
        flair_text = "Information"
        flair_choices = subreddit.flair.link_templates
        flair_template_id = None
        
        # Find the "Information" flair
        for flair in flair_choices:
            if flair['text'] == flair_text:
                flair_template_id = flair['id']
                break
        
        # Ensure flair is found
        if flair_template_id:
            # Submit the post with the flair applied
            submission = subreddit.submit(
                title=title,
                url=url,
                flair_id=flair_template_id  # Set flair at the time of submission
            )
            print(f"Posted to r/{reddit_subreddit}: {submission.title} - {submission.url}")
        else:
            print(f"Flair '{flair_text}' not found.")
    
    except Exception as e:
        print(f"An error occurred while posting to Reddit: {e}")


def run_task():
    print("Checking for news...")
    skip_links = []  # Keep track of links we've already skipped

    while True:
        link = get_first_news_link("https://www.nexon.com/maplestory/news/all?page=1", skip_links=skip_links)
        
        if not link:
            print("No new link found or end of task.")
            break

        print(f"Getting title for: {link}")
        name = get_title(link)
        print(f"Title: {name}")

        forbidden_keywords = ["[UPDATED", "[COMPLETED", "MAINTENANCE", "ART CORNER","SCHEDULED","PATCH NOTES CHAT CLOSURE"]

        if name is not None and not any(keyword in name for keyword in forbidden_keywords):
            # Save the new URL to news.txt before posting
            with open('news.txt', 'a') as file:
                file.write(link + '\n')
            
            post_to_reddit(link, name)
            break  # Exit the loop after successfully posting
        else:
            print(f"Skipped due to forbidden keyword or title is None: {name}")
            skip_links.append(link)  # Add this link to the skip list

    print("End task")

# Schedule the task at xx:00 and xx:30
schedule.every().hour.at(":00").do(run_task)  # Run at every xx:00
schedule.every().hour.at(":35").do(run_task)  # Run at every xx:30

if __name__ == "__main__":
    print("launching and doing initial check")
    run_task()
    while True:
        schedule.run_pending()  # Run pending scheduled tasks
        time.sleep(1)  # Wait 1 second before checking again
