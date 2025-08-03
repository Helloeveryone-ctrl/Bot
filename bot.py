#!/usr/bin/env python3
import pywikibot
from pywikibot import pagegenerators, config2
import datetime
import logging
import os
import sys

# Configure logging
logging.basicConfig(
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def fetch_unpatrolled_pages(site, limit=100):
    """
    Fetch pages from recent changes that are unpatrolled.
    Returns a list of unique page titles.
    """
    logger.info("Fetching unpatrolled pages (limit=%d)...", limit)
    try:
        rc_gen = site.recentchanges(
            namespace=0,  # main/article namespace only
            changetype='edit',
            patrolled=False,
            total=limit,
            reverse=False
        )
        titles = set()
        for change in rc_gen:
            title = change['title']
            if title not in titles:
                titles.add(title)
        logger.info(f"Fetched {len(titles)} unpatrolled pages.")
        return sorted(titles)
    except Exception as e:
        logger.error("Error fetching unpatrolled pages: %s", e)
        return []

def build_wikitext(pages):
    """
    Builds wikitext content for the patrolling page.
    """
    date_str = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    header = f"== Pages needing patrolling (updated on {date_str}) ==\n\n"
    if not pages:
        return header + "No pages currently need patrolling.\n"
    else:
        lines = [f"* [[{title}]]" for title in pages]
        return header + "\n".join(lines) + "\n"

def main():
    # Read config from environment variables (for GitHub Actions)
    site_family = os.getenv('WIKI_FAMILY', 'wikipedia')
    site_lang = os.getenv('WIKI_LANG', 'test')  # test Wikipedia
    target_page_title = os.getenv('TARGET_PAGE', 'User:Cactusisme/patrolling articles')
    unpatrolled_limit = int(os.getenv('UNPATROLLED_LIMIT', '100'))

    logger.info(f"Starting bot on {site_lang}.{site_family} updating {target_page_title}")

    # Setup site and login
    site = pywikibot.Site(site_lang, site_family)
    site.login()

    # Fetch unpatrolled pages
    pages = fetch_unpatrolled_pages(site, limit=unpatrolled_limit)

    # Build wikitext content
    content = build_wikitext(pages)

    # Prepare page object and save
    target_page = pywikibot.Page(site, target_page_title)
    summary = "Bot update: list of pages needing patrolling"

    try:
        current_text = target_page.text
        if current_text == content:
            logger.info("No change in content detected. Skipping save.")
            return
        target_page.text = content
        target_page.save(summary=summary)
        logger.info("Page updated successfully.")
    except pywikibot.exceptions.Error as e:
        logger.error(f"Failed to save page: {e}")

if __name__ == '__main__':
    main()
