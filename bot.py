#!/usr/bin/env python3
import pywikibot
from pywikibot import pagegenerators
import datetime
import logging
import sys

# Setup logging to stdout
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

def fetch_unpatrolled_pages(site, limit=100):
    logger.info(f"Fetching up to {limit} unpatrolled pages from recent changes...")
    try:
        rc_gen = site.recentchanges(
            namespace=0,  # main namespace
            changetype='edit',
            patrolled=False,
            total=limit,
        )
        titles = set()
        for change in rc_gen:
            titles.add(change['title'])
        logger.info(f"Found {len(titles)} unpatrolled pages.")
        return sorted(titles)
    except Exception as e:
        logger.error(f"Error fetching unpatrolled pages: {e}")
        return []

def build_wikitext(pages):
    now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    header = f"== Pages needing patrolling (updated on {now}) ==\n\n"
    if not pages:
        return header + "No pages currently need patrolling.\n"
    lines = [f"* [[{title}]]" for title in pages]
    return header + "\n".join(lines) + "\n"

def main():
    site = pywikibot.Site('test', 'wikipedia')
    site.login()

    target_page_title = 'User:Cactusisme/patrolling articles'
    target_page = pywikibot.Page(site, target_page_title)

    pages = fetch_unpatrolled_pages(site, limit=100)
    new_text = build_wikitext(pages)

    try:
        if target_page.text != new_text:
            target_page.text = new_text
            target_page.save(summary="Bot update: list of pages needing patrolling")
            logger.info(f"Successfully updated {target_page_title}")
        else:
            logger.info("No changes detected, not saving.")
    except Exception as e:
        logger.error(f"Failed to save page: {e}")

if __name__ == '__main__':
    main()
