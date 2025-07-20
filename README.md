# MapleStory News Bot

A Python bot that automatically monitors the official MapleStory news page and posts new announcements to the r/maplestory subreddit on Reddit.

## Features

- **Automated News Monitoring**: Checks the MapleStory news page every 35 minutes
- **Smart Filtering**: Filters out maintenance notices, updates, and other non-essential posts
- **Duplicate Prevention**: Tracks posted links and checks recent subreddit posts to avoid duplicates
- **Auto-Flair**: Automatically applies "Information" flair to Reddit posts
- **Headless Operation**: Runs in the background using headless Chrome

## How It Works

1. **Web Scraping**: Uses Selenium to scrape the MapleStory news page
2. **Content Filtering**: Filters out posts containing keywords like "MAINTENANCE", "UPDATED", etc.
3. **Reddit Integration**: Posts filtered news to r/maplestory using the Reddit API
4. **Scheduling**: Runs automatically at :00 and :35 minutes of every hour

## Prerequisites

- Python 3.7+
- Chrome browser
- ChromeDriver (configured for `/usr/bin/chromedriver`)
- Reddit API credentials

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd maplestory-news-bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your Reddit API credentials:
```env
REDDIT_USERNAME=your_reddit_username
REDDIT_PASSWORD=your_reddit_password
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=MapleStoryNewsBot/1.0
```

## Reddit API Setup

1. Go to [Reddit App Preferences](https://www.reddit.com/prefs/apps)
2. Click "Create App" or "Create Another App"
3. Choose "script" as the app type
4. Note down your client ID and client secret
5. Add these credentials to your `.env` file

## Usage

Run the bot:
```bash
python bot.py
```

The bot will:
- Perform an initial check for new news
- Schedule automatic checks every 35 minutes
- Log all activities to the console
- Track posted links in `news.txt`

## Configuration

### Filtered Keywords
The bot automatically filters out posts containing these keywords:
- `[UPDATED`
- `[COMPLETED`
- `MAINTENANCE`
- `ART CORNER`
- `SCHEDULED`
- `PATCH NOTES CHAT CLOSURE`
- `[UPDATE]`

Posts starting with "update", "updated", "complete", or "completed" are also filtered out.

### Subreddit
Currently configured to post to `r/maplestory`. Change the `reddit_subreddit` variable to post elsewhere.

## File Structure

- `bot.py` - Main bot script
- `requirements.txt` - Python dependencies
- `news.txt` - Tracks posted news links
- `.env` - Environment variables (create this file)

## Dependencies

Key dependencies include:
- `selenium` - Web scraping
- `beautifulsoup4` - HTML parsing
- `praw` - Reddit API wrapper
- `schedule` - Task scheduling
- `python-dotenv` - Environment variable management

## Troubleshooting

### ChromeDriver Issues
- Ensure ChromeDriver is installed at `/usr/bin/chromedriver`
- Update the `service` path in the code if your ChromeDriver is elsewhere

### Reddit API Errors
- Verify your Reddit credentials in the `.env` file
- Check that your Reddit account has sufficient karma/age
- Ensure your app is configured as a "script" type

### No News Found
- The bot only checks the first 3 news items
- Filtered content won't be posted
- Check console output for debugging information

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is open source and available under the [MIT License](LICENSE).