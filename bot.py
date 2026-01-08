import os
import re
import shutil
import tempfile

# Set custom temp directory before other imports that might use it
temp_dir = os.path.join(os.path.dirname(__file__), 'tmp')
os.makedirs(temp_dir, exist_ok=True)
os.environ['TMPDIR'] = temp_dir
tempfile.tempdir = temp_dir

from dotenv import load_dotenv
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.remote_connection import LOGGER
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

    # Try Chrome first, fall back to Firefox if it fails
    driver = None
    try:
        chrome_options = ChromeOptions()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-software-rasterizer')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-setuid-sandbox')
        chrome_options.add_argument('--single-process')
        chrome_options.add_argument('--window-size=1280x720')
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--disable-logging')
        chrome_options.add_argument('--log-level=3')
        chrome_options.add_argument('--silent')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.binary_location = '/usr/bin/chromium'

        service = ChromeService('/usr/bin/chromedriver')
        driver = webdriver.Chrome(service=service, options=chrome_options)
        print("Using Chrome driver")
    except Exception as chrome_error:
        print(f"Chrome driver failed: {chrome_error}")
        print("Falling back to Firefox driver...")
        try:
            firefox_options = FirefoxOptions()
            firefox_options.add_argument("--headless")
            firefox_options.add_argument('--width=1280')
            firefox_options.add_argument('--height=720')

            # Find geckodriver in PATH
            geckodriver_path = shutil.which('geckodriver')
            if geckodriver_path:
                print(f"Found geckodriver at: {geckodriver_path}")
                service = FirefoxService(executable_path=geckodriver_path)
                driver = webdriver.Firefox(service=service, options=firefox_options)
            else:
                print("geckodriver not found in PATH, trying default")
                driver = webdriver.Firefox(options=firefox_options)
            print("Using Firefox driver")
        except Exception as firefox_error:
            print(f"Firefox driver also failed: {firefox_error}")
            return None

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
        if driver:
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

def get_title(url):
    """
    Extract title from URL by taking everything after the last '/',
    removing dashes, and capitalizing each word.

    Example:
    https://www.nexon.com/maplestory/news/maintenance/28117/v-260-known-issues
    -> "V 260 Known Issues"

    https://www.nexon.com/maplestory/news/update/12345/what-s-your-maple-story
    -> "Whats Your Maple Story"
    """
    try:
        # Get everything after the last '/'
        title_part = url.split('/')[-1]

        # Handle common contractions by replacing specific patterns before splitting
        # This treats "what-s" as "whats" instead of "what s"
        contractions = {
            '-s-': 's ',      # what-s-your -> whats your
            '-t-': 't ',      # don-t-miss -> dont miss
            '-re-': 're ',    # you-re-ready -> youre ready
            '-ll-': 'll ',    # we-ll-see -> well see
            '-ve-': 've ',    # you-ve-got -> youve got
            '-d-': 'd ',      # you-d-better -> youd better
            '-m-': 'm ',      # i-m-here -> im here
        }

        for pattern, replacement in contractions.items():
            title_part = title_part.replace(pattern, replacement)

        # Replace remaining dashes with spaces
        title = title_part.replace('-', ' ')

        # Capitalize the first letter of each word
        title = title.title()

        return title

    except Exception as e:
        print(f"An error occurred in get_title: {e}")
        return None

def check_if_url_in_recent_posts(url, limit=10):
    """
    Check if the URL has been posted in the recent posts of the subreddit
    
    Args:
        url (str): The URL to check
        limit (int): Number of recent posts to check (default: 10)
    
    Returns:
        bool: True if URL found in recent posts, False otherwise
    """
    try:
        # Initialize Reddit API connection
        reddit = praw.Reddit(
            client_id=reddit_client_id,
            client_secret=reddit_client_secret,
            user_agent=reddit_user_agent,
            username=reddit_username,
            password=reddit_password
        )
        
        # Access the subreddit
        subreddit = reddit.subreddit(reddit_subreddit)
        
        # Check recent posts
        for submission in subreddit.new(limit=limit):
            if submission.url == url:
                print(f"URL already posted recently: {url}")
                return True
                
        return False
    
    except Exception as e:
        print(f"Error checking recent posts: {e}")
        # If there's an error, we'll assume it's not a duplicate to be safe
        return False

def post_to_reddit(url, name):
    # First check if this URL was recently posted
    if check_if_url_in_recent_posts(url):
        print(f"Skipping post as URL was found in recent posts: {url}")
        return False

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
            return True
        else:
            print(f"Flair '{flair_text}' not found.")
            return False
    
    except Exception as e:
        print(f"An error occurred while posting to Reddit: {e}")
        return False


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
        forbidden_keywords = ["[UPDATED", "[COMPLETED", "MAINTENANCE", "ART CORNER","SCHEDULED","PATCH NOTES CHAT CLOSURE","[UPDATE]"]
       
        # Check if title starts with "update" or "updated" (case-insensitive)
        starts_with_forbidden = False
        if name is not None:
            name_lower = name.lower()
            forbidden_prefixes = ["update", "updated", "complete", "completed"]
            if any(name_lower.startswith(prefix) for prefix in forbidden_prefixes):
                starts_with_forbidden = True
        
        # Check for forbidden keywords with case-insensitive comparison
        contains_forbidden_keyword = False
        if name is not None:
            name_lower = name.lower()
            forbidden_keywords_lower = [keyword.lower() for keyword in forbidden_keywords]
            if any(keyword_lower in name_lower for keyword_lower in forbidden_keywords_lower):
                contains_forbidden_keyword = True
        
        if name is not None and not contains_forbidden_keyword and not starts_with_forbidden:
            # Check if URL is already in recent subreddit posts
            if check_if_url_in_recent_posts(link):
                print(f"URL {link} already posted recently. Skipping...")
                skip_links.append(link)
                continue
               
            # Save the new URL to news.txt before posting
            with open('news.txt', 'a') as file:
                file.write(link + '\n')
           
            post_success = post_to_reddit(link, name)
            if post_success:
                break  # Exit the loop after successfully posting
            else:
                skip_links.append(link)  # Add this link to skip list if posting failed
        else:
            if starts_with_forbidden:
                print(f"Skipped due to title starting with 'update' or 'updated': {name}")
            elif contains_forbidden_keyword:
                print(f"Skipped due to forbidden keyword: {name}")
            else:
                print(f"Skipped due to title is None: {name}")
            skip_links.append(link)  # Add this link to the skip list
    print("End task")

# Schedule the task at xx:00 and xx:35
schedule.every().hour.at(":00").do(run_task)  # Run at every xx:00
schedule.every().hour.at(":35").do(run_task)  # Run at every xx:35

if __name__ == "__main__":
    print("launching and doing initial check")
    run_task()
    while True:
        schedule.run_pending()  # Run pending scheduled tasks
        time.sleep(1)  # Wait 1 second before checking again