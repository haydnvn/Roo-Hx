import os
import re
import shutil
import sys
from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit
import tempfile

# POSIX-only. The bot runs on Linux (Raspberry Pi); this import is guarded so
# the module still loads on Windows for editing, with locking disabled.
try:
    import fcntl
except ImportError:
    fcntl = None

# Set custom temp directory before other imports that might use it
temp_dir = os.path.join(os.path.dirname(__file__), 'tmp')
os.makedirs(temp_dir, exist_ok=True)
os.environ['TMPDIR'] = temp_dir
tempfile.tempdir = temp_dir

from dotenv import load_dotenv
import logging
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.remote_connection import LOGGER
import praw
import schedule
import time

# Load environment variables from .env file
load_dotenv()

# Reddit credentials from environment variables
reddit_username = os.getenv('REDDIT_USERNAME')
reddit_password = os.getenv('REDDIT_PASSWORD')
reddit_client_id = os.getenv('REDDIT_CLIENT_ID')
reddit_client_secret = os.getenv('REDDIT_CLIENT_SECRET')
reddit_user_agent = os.getenv('REDDIT_USER_AGENT')
reddit_subreddit = ('maplestory')

# Anchor all state to the script's own directory. These were previously bare
# relative paths, so the dedup memory silently depended on the working
# directory the bot happened to be launched from - a launch from anywhere
# else started with a blank memory and re-posted everything on the front page.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NEWS_FILE = os.path.join(BASE_DIR, 'news.txt')
INSTANCE_LOCK_FILE = os.path.join(BASE_DIR, '.bot.instance.lock')
POST_LOCK_FILE = os.path.join(BASE_DIR, '.bot.post.lock')


def normalize_url(url):
    """Strip query string and fragment so tracking params don't defeat dedup.

    Also drops a trailing slash and lowercases the host, so the same article
    can't slip through dedup under two spellings.
    """
    parts = urlsplit(url)
    path = parts.path.rstrip('/')
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, '', ''))


def load_posted_links():
    """Return the set of already-posted links, normalized.

    Normalizing on read matters as much as on write: entries recorded before
    normalize_url existed carry query strings, and would otherwise never match
    a freshly normalized link - re-posting that article.
    """
    if not os.path.exists(NEWS_FILE):
        return set()
    with open(NEWS_FILE, 'r') as file:
        return {normalize_url(line.strip()) for line in file if line.strip()}


def record_posted_link(link):
    """Append a link to the posted-links file and flush it to disk.

    fsync is deliberate: on a Pi that can lose power, a link buffered in the
    page cache but never written is a link that gets posted a second time
    after reboot.
    """
    with open(NEWS_FILE, 'a') as file:
        file.write(normalize_url(link) + '\n')
        file.flush()
        os.fsync(file.fileno())


@contextmanager
def file_lock(path, description):
    """Hold an exclusive advisory lock on `path` for the duration of the block.

    Serializes the post critical section across processes, so two bots can
    never interleave "check news.txt" and "submit to Reddit".
    """
    if fcntl is None:
        yield True
        return
    handle = open(path, 'w')
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield True
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def acquire_single_instance_lock():
    """Exit if another copy of the bot is already running.

    This is the primary duplicate-post defence and it lives here, in the bot
    itself, rather than in the launcher - so it holds no matter how the bot
    was started: tmux, cron, systemd, or by hand during a deploy. The lock is
    released automatically by the OS when the process dies, including on
    SIGKILL, so a crashed bot never leaves the lock stuck.
    """
    if fcntl is None:
        print("WARNING: file locking unavailable on this platform; "
              "single-instance protection is DISABLED")
        return None
    handle = open(INSTANCE_LOCK_FILE, 'w')
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Another instance of the bot is already running. Exiting to "
              "avoid duplicate posts.")
        handle.close()
        sys.exit(0)
    handle.write(str(os.getpid()))
    handle.flush()
    # Deliberately leaked: the lock must be held for the process's lifetime.
    return handle

def get_reddit():
    """Return a Reddit client, reusing one connection for the whole process.

    Previously every dedup check and every post built a fresh praw.Reddit and
    re-authenticated. That tripled the API traffic per candidate and made
    rate-limit errors likelier - which used to mean the dedup checks failed
    and the bot posted anyway.
    """
    if get_reddit._client is None:
        get_reddit._client = praw.Reddit(
            client_id=reddit_client_id,
            client_secret=reddit_client_secret,
            user_agent=reddit_user_agent,
            username=reddit_username,
            password=reddit_password
        )
    return get_reddit._client


get_reddit._client = None


def get_first_news_link(url, skip_links=[]):
    # Note: this is only a first-pass filter to pick a candidate. It is NOT
    # the authority on whether something has been posted - news.txt is re-read
    # under lock immediately before submitting (see run_task), because the
    # scrape below takes 1-2 minutes and another process may post during it.
    posted_links = load_posted_links()

    # Create Firefox driver
    firefox_options = FirefoxOptions()
    firefox_options.add_argument("--headless")
    firefox_options.add_argument('--width=1280')
    firefox_options.add_argument('--height=720')

    geckodriver_path = shutil.which('geckodriver')
    if geckodriver_path:
        service = FirefoxService(executable_path=geckodriver_path)
        driver = webdriver.Firefox(service=service, options=firefox_options)
    else:
        driver = webdriver.Firefox(options=firefox_options)

    try:
        # Navigate to the URL
        driver.get(url)

        # The news list is a Vue app; cards render as plain <div class="news-summary">
        # elements with no href/data-id anywhere in the DOM - navigation only
        # happens via a JS click handler. So we click each card and read the
        # resulting URL instead of scraping an href.
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.news-summary"))
        )

        article_url_pattern = re.compile(r"https://www\.nexon\.com/maplestory/news/[\w-]+/\d+/[\w-]+")

        news_links = []
        for i in range(3):
            cards = driver.find_elements(By.CSS_SELECTOR, "div.news-summary")
            if i >= len(cards):
                break

            card = cards[i]
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
            driver.execute_script("arguments[0].click();", card)

            try:
                WebDriverWait(driver, 10).until(
                    lambda d: d.current_url != url and article_url_pattern.match(d.current_url)
                )
                news_links.append(normalize_url(driver.current_url))
            except Exception as e:
                print(f"Timed out waiting for navigation after clicking card {i}: {e}")

            driver.get(url)
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.news-summary"))
            )

        # Check only the first three links
        print(f"All found links: {news_links}")
        first_three_links = news_links[:3]
        print(f"Checking these first 3: {first_three_links}")
        # Filter out links already posted or skipped
        filtered_links = [
            link for link in first_three_links
            if link not in posted_links and link not in skip_links
        ]

        # Return the first non-skipped and non-posted link. Note: this does
        # NOT write to news.txt - that only happens once the link is
        # actually confirmed posted to Reddit (see run_task), so a link
        # that's found but later rejected/fails isn't falsely marked done.
        if filtered_links:
            first_news_link = filtered_links[0]
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
        bool: True if URL found in recent posts (or if the check failed),
              False only when the check ran and found nothing.
    """
    try:
        subreddit = get_reddit().subreddit(reddit_subreddit)

        # Check recent posts
        normalized_url = normalize_url(url)
        for submission in subreddit.new(limit=limit):
            if normalize_url(submission.url) == normalized_url:
                print(f"URL already posted recently: {url}")
                return True

        return False

    except Exception as e:
        print(f"Error checking recent posts: {e}")
        # Fail CLOSED. This previously returned False ("not a duplicate") on
        # any error, so a rate-limit or network blip disabled the check and
        # the bot posted regardless. Skipping a cycle costs one article for
        # 35 minutes; a duplicate is permanent and public.
        return True

def check_if_already_posted_by_me(url, limit=200):
    """
    Check the bot account's own submission history for this URL.

    Unlike check_if_url_in_recent_posts (which only looks at the last N
    posts to the subreddit from anyone), this checks the account's own
    posts directly, so it isn't affected by other users posting in
    between and catches duplicates even if news.txt was lost/reset.

    Args:
        url (str): The URL to check
        limit (int): Number of recent submissions by this account to check
                     (default: 200, several weeks of posting at 2 checks/hour)

    Returns:
        bool: True if this account already posted the URL (or if the check
              failed), False only when the check ran and found nothing.
    """
    try:
        normalized_url = normalize_url(url)
        for submission in get_reddit().user.me().submissions.new(limit=limit):
            if normalize_url(submission.url) == normalized_url:
                print(f"URL already posted by this account: {url}")
                return True

        return False

    except Exception as e:
        print(f"Error checking own submission history: {e}")
        # Fail CLOSED - see the note in check_if_url_in_recent_posts.
        return True

def post_to_reddit(url, name):
    # Duplicate checks deliberately do NOT live here. They run in run_task,
    # inside the same lock that claims the link in news.txt, so nothing can
    # happen between "confirmed not a duplicate" and "submitted".
    reddit = get_reddit()

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

        # Safety net: never post anything that isn't a real article URL
        # (e.g. the news listing page itself, if scraping ever misfires).
        if not re.match(r"https://www\.nexon\.com/maplestory/news/[\w-]+/\d+/[\w-]+", link):
            print(f"Skipping malformed/non-article link: {link}")
            skip_links.append(link)
            continue

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
            # Everything from here to the submit runs under one lock, with no
            # slow work inside it. The scrape above takes 1-2 minutes, so the
            # posted_links snapshot it used is stale by now and must not be
            # trusted; we re-read under the lock instead.
            with file_lock(POST_LOCK_FILE, "post"):
                if normalize_url(link) in load_posted_links():
                    print(f"URL {link} was posted while we were scraping. Skipping...")
                    skip_links.append(link)
                    continue

                if check_if_already_posted_by_me(link):
                    print(f"URL {link} already in this account's history. Skipping...")
                    record_posted_link(link)
                    skip_links.append(link)
                    continue

                if check_if_url_in_recent_posts(link):
                    print(f"URL {link} already posted recently. Skipping...")
                    skip_links.append(link)
                    continue

                # Claim the link BEFORE submitting, not after. If the bot dies
                # between submit and record - power cut, SIGKILL, crash - a
                # record-after design re-posts the article on restart. The
                # trade is deliberate: a failed submit costs one missed
                # article (recoverable by deleting the line from news.txt),
                # whereas a duplicate is public and permanent.
                record_posted_link(link)
                post_success = post_to_reddit(link, name)

            if post_success:
                break  # Exit the loop after successfully posting
            else:
                print(f"WARNING: {link} was claimed in {NEWS_FILE} but posting "
                      f"failed. It will not be retried. Remove that line "
                      f"manually if you want the bot to try again.")
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
    # Must come first: refuses to start if another bot is already running,
    # regardless of how this one was launched. Held for the process lifetime.
    _instance_lock = acquire_single_instance_lock()

    print("launching and doing initial check")
    run_task()
    while True:
        schedule.run_pending()  # Run pending scheduled tasks
        time.sleep(1)  # Wait 1 second before checking again