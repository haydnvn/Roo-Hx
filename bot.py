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
import praw
import schedule
import time
from bs4 import BeautifulSoup
import requests
import gc  # Garbage collection for memory management

# Load environment variables from .env file
load_dotenv()

# Reddit credentials from environment variables
reddit_username = os.getenv('REDDIT_USERNAME')
reddit_password = os.getenv('REDDIT_PASSWORD')
reddit_client_id = os.getenv('REDDIT_CLIENT_ID')
reddit_client_secret = os.getenv('REDDIT_CLIENT_SECRET')
reddit_user_agent = os.getenv('REDDIT_USER_AGENT')
reddit_subreddit = ('maplestory')

def create_minimal_driver():
    """Create a Chrome driver optimized for Raspberry Pi with minimal memory usage"""
    chrome_options = Options()
    
    # Essential headless options
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Aggressive memory optimization for Raspberry Pi
    chrome_options.add_argument("--memory-pressure-off")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    chrome_options.add_argument("--disable-renderer-backgrounding")
    chrome_options.add_argument("--disable-features=TranslateUI")
    chrome_options.add_argument("--disable-ipc-flooding-protection")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-preconnect-resource-hints")
    chrome_options.add_argument("--disable-prefetch-scan-result")
    chrome_options.add_argument("--disable-print-preview")
    chrome_options.add_argument("--disable-web-security")
    
    # Disable media and images to save memory
    chrome_options.add_argument("--disable-images")
    chrome_options.add_argument("--disable-javascript")  # Only if site works without JS
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-java")
    chrome_options.add_argument("--disable-audio-output")
    
    # Set very small window size
    chrome_options.add_argument("--window-size=800,600")
    
    # Memory limits
    chrome_options.add_argument("--max_old_space_size=512")  # Limit to 512MB
    chrome_options.add_argument("--memory-pressure-off")
    
    # Performance optimizations
    chrome_options.add_argument("--aggressive-cache-discard")
    chrome_options.add_argument("--disable-background-mode")
    chrome_options.add_argument("--disable-client-side-phishing-detection")
    chrome_options.add_argument("--disable-component-update")
    chrome_options.add_argument("--disable-hang-monitor")
    chrome_options.add_argument("--disable-prompt-on-repost")
    
    # Prefs to disable more features
    prefs = {
        "profile.default_content_setting_values": {
            "images": 2,  # Block images
            "plugins": 2,  # Block plugins
            "popups": 2,  # Block popups
            "geolocation": 2,  # Block location sharing
            "notifications": 2,  # Block notifications
            "media_stream": 2,  # Block media stream
        },
        "profile.managed_default_content_settings": {
            "images": 2
        }
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    service = Service('/usr/bin/chromedriver')
    return webdriver.Chrome(service=service, options=chrome_options)

def get_first_news_link_requests(url, skip_links=[]):
    """Alternative method using requests instead of Selenium - much lighter on memory"""
    # Load previously posted links from news.txt
    posted_links = set()
    if os.path.exists('news.txt'):
        with open('news.txt', 'r') as file:
            posted_links = set(line.strip() for line in file.readlines())

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        print("Fetching page with requests (memory-efficient method)...")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Use BeautifulSoup to parse the HTML
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find all anchor tags with href containing "/maplestory/news/"
        news_links = [
            "https://www.nexon.com" + a_tag['href']
            for a_tag in soup.find_all('a', href=True)
            if "/maplestory/news/" in a_tag['href']
        ]

        # Check only the first three links
        first_three_links = news_links[:3]
        print(f"Found links: {first_three_links}")
        
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
        print(f"Error with requests method: {e}")
        return None

def get_first_news_link_selenium(url, skip_links=[], max_retries=2):
    """Selenium method with heavy memory optimization for Raspberry Pi"""
    # Load previously posted links from news.txt
    posted_links = set()
    if os.path.exists('news.txt'):
        with open('news.txt', 'r') as file:
            posted_links = set(line.strip() for line in file.readlines())

    driver = None
    for attempt in range(max_retries):
        try:
            print(f"Selenium attempt {attempt + 1} of {max_retries}")
            
            # Force garbage collection before creating driver
            gc.collect()
            
            driver = create_minimal_driver()
            
            # Set very short timeouts for Raspberry Pi
            driver.set_page_load_timeout(20)
            driver.implicitly_wait(5)
            
            # Navigate to the URL
            driver.get(url)
            
            # Minimal wait
            time.sleep(1)

            # Get the page source quickly
            page_source = driver.page_source
            
            # Close driver immediately to free memory
            driver.quit()
            driver = None
            
            # Force garbage collection
            gc.collect()

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
            print(f"Found links: {first_three_links}")
            
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
            print(f"Selenium attempt {attempt + 1} failed with error: {e}")
            if attempt == max_retries - 1:
                print("All selenium attempts failed, trying requests method...")
                return get_first_news_link_requests(url, skip_links)
            time.sleep(3)  # Short wait before retry
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            # Always force garbage collection
            gc.collect()

def parse_url_title(url):
    """Parse title from URL pattern"""
    pattern = r"https://www\.nexon\.com/maplestory/news/\w+/\d{5}/([\w-]+)"
    match = re.search(pattern, url)
    
    if match:
        title = match.group(1).replace('-', ' ')
        return title.title()
    
    return None

def get_title_requests(url):
    """Get title using requests - much more memory efficient"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        print("Getting title with requests (memory-efficient method)...")
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Try multiple selectors for the title
        title_selectors = [
            ".news-detail__title.title.xs",
            ".news-detail__title",
            "h1.title",
            "h1",
            "title"
        ]
        
        for selector in title_selectors:
            title_element = soup.select_one(selector)
            if title_element:
                title = title_element.get_text().strip()
                if title:
                    return title
        
        # Fallback to URL parsing
        return parse_url_title(url)
        
    except Exception as e:
        print(f"Error getting title with requests: {e}")
        return parse_url_title(url)

def get_title_selenium(url, max_retries=2):
    """Get title with Selenium as fallback - optimized for Raspberry Pi"""
    driver = None
    for attempt in range(max_retries):
        try:
            print(f"Getting title with Selenium - Attempt {attempt + 1} of {max_retries}")
            
            # Force garbage collection
            gc.collect()
            
            driver = create_minimal_driver()
            
            # Set short timeouts
            driver.set_page_load_timeout(15)
            driver.implicitly_wait(3)

            # Navigate to the desired webpage
            driver.get(url)

            # Wait for the title to be present
            title_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".news-detail__title.title.xs"))
            )

            # Get the text from the title element
            title = title_element.text.strip()

            if title:
                return title
            else:
                return parse_url_title(url)

        except Exception as e:
            print(f"Selenium title attempt {attempt + 1} failed with error: {e}")
            if attempt == max_retries - 1:
                print("All selenium title attempts failed, using URL parsing fallback")
                return parse_url_title(url)
            time.sleep(2)
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            gc.collect()

def get_title(url):
    """Get title - try requests first, then selenium as fallback"""
    # Try requests first (much more memory efficient)
    title = get_title_requests(url)
    if title:
        return title
    
    # Fallback to selenium if requests fails
    print("Requests method failed, trying Selenium...")
    return get_title_selenium(url)

def check_if_url_in_recent_posts(url, limit=10):
    """Check if the URL has been posted in the recent posts of the subreddit"""
    try:
        reddit = praw.Reddit(
            client_id=reddit_client_id,
            client_secret=reddit_client_secret,
            user_agent=reddit_user_agent,
            username=reddit_username,
            password=reddit_password
        )
        
        subreddit = reddit.subreddit(reddit_subreddit)
        
        for submission in subreddit.new(limit=limit):
            if submission.url == url:
                print(f"URL already posted recently: {url}")
                return True
                
        return False
    
    except Exception as e:
        print(f"Error checking recent posts: {e}")
        return False

def post_to_reddit(url, name):
    """Post to Reddit with error handling"""
    if check_if_url_in_recent_posts(url):
        print(f"Skipping post as URL was found in recent posts: {url}")
        return False

    try:
        reddit = praw.Reddit(
            client_id=reddit_client_id,
            client_secret=reddit_client_secret,
            user_agent=reddit_user_agent,
            username=reddit_username,
            password=reddit_password
        )
        print("Logged in to Reddit")

        title = name
        subreddit = reddit.subreddit(reddit_subreddit)
        
        # Set the "Information" flair
        flair_text = "Information"
        flair_choices = subreddit.flair.link_templates
        flair_template_id = None
        
        for flair in flair_choices:
            if flair['text'] == flair_text:
                flair_template_id = flair['id']
                break
        
        if flair_template_id:
            submission = subreddit.submit(
                title=title,
                url=url,
                flair_id=flair_template_id
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
    """Main task runner optimized for Raspberry Pi"""
    print("Checking for news... (Raspberry Pi optimized)")
    skip_links = []

    # Force garbage collection at start
    gc.collect()

    while True:
        try:
            # Try requests method first, then selenium as fallback
            link = get_first_news_link_requests("https://www.nexon.com/maplestory/news/all?page=1", skip_links=skip_links)
            
            if not link:
                print("Requests method failed, trying Selenium...")
                link = get_first_news_link_selenium("https://www.nexon.com/maplestory/news/all?page=1", skip_links=skip_links)
            
            if not link:
                print("No new link found or end of task.")
                break

            print(f"Getting title for: {link}")
            name = get_title(link)
            print(f"Title: {name}")

            forbidden_keywords = ["[UPDATED", "[COMPLETED", "MAINTENANCE", "ART CORNER","SCHEDULED","PATCH NOTES CHAT CLOSURE","[UPDATE]"]

            if name is not None and not any(keyword in name for keyword in forbidden_keywords):
                if check_if_url_in_recent_posts(link):
                    print(f"URL {link} already posted recently. Skipping...")
                    skip_links.append(link)
                    continue
                    
                # Save the new URL to news.txt before posting
                with open('news.txt', 'a') as file:
                    file.write(link + '\n')
                
                post_success = post_to_reddit(link, name)
                if post_success:
                    break
                else:
                    skip_links.append(link)
            else:
                print(f"Skipped due to forbidden keyword or title is None: {name}")
                skip_links.append(link)
                
            # Force garbage collection between iterations
            gc.collect()

        except Exception as e:
            print(f"Error in run_task: {e}")
            time.sleep(10)
            break

    print("End task")
    # Final garbage collection
    gc.collect()

# Schedule the task at xx:00 and xx:35
schedule.every().hour.at(":00").do(run_task)
schedule.every().hour.at(":35").do(run_task)

if __name__ == "__main__":
    print("Launching Raspberry Pi optimized bot with initial check")
    try:
        run_task()
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    except KeyboardInterrupt:
        print("Script stopped by user")
    except Exception as e:
        print(f"Unexpected error: {e}")
        time.sleep(300)  # Wait 5 minutes before restarting