import os
import requests
import sys
import re
import datetime

API_URL = "https://en.wikipedia.org/w/api.php"

HEADERS = {
    'User-Agent': 'Fixinbot/1.0 (https://en.wikipedia.org/wiki/User:Fixinbot)'
}

def login_and_get_session(username, password):
    session = requests.Session()
    session.headers.update(HEADERS)

    r1 = session.get(API_URL, params={
        'action': 'query',
        'meta': 'tokens',
        'type': 'login',
        'format': 'json'
    })
    login_token = r1.json()['query']['tokens']['logintoken']

    r2 = session.post(API_URL, data={
        'action': 'login',
        'lgname': username,
        'lgpassword': password,
        'lgtoken': login_token,
        'format': 'json'
    })

    result = r2.json()
    if result['login']['result'] != 'Success':
        print(f"❌ Login failed: {result}")
        sys.exit(1)

    r3 = session.get(API_URL, params={
        'action': 'query',
        'meta': 'userinfo',
        'format': 'json'
    })
    user = r3.json()['query']['userinfo']['name']
    print(f"✅ Logged in as {user}")
    return session

def get_csrf_token(session):
    r = session.get(API_URL, params={
        'action': 'query',
        'meta': 'tokens',
        'format': 'json'
    })
    return r.json()['query']['tokens']['csrftoken']

def get_current_page_text(session, title):
    r = session.get(API_URL, params={
        'action': 'query',
        'prop': 'revisions',
        'titles': title,
        'rvprop': 'content',
        'format': 'json'
    })
    pages = r.json()['query']['pages']
    for page_id in pages:
        return pages[page_id].get('revisions', [{}])[0].get('*', '')
    return ''

def check_pages_exist(session, titles):
    """Batch check existence of pages. Returns set of titles that exist."""
    existing = set()
    max_batch = 50
    for i in range(0, len(titles), max_batch):
        batch = titles[i:i+max_batch]
        params = {
            'action': 'query',
            'titles': '|'.join(batch),
            'format': 'json'
        }
        r = session.get(API_URL, params=params)
        data = r.json()
        pages = data.get('query', {}).get('pages', {})
        for page_id, page in pages.items():
            if int(page_id) > 0:
                existing.add(page['title'])
    return existing

def extract_titles_in_lines(lines):
    """Extract page titles from lines like '* [[Page title]]'."""
    titles = []
    line_map = []
    pattern = re.compile(r'^\*\s*\[\[(.+?)(?:\|.+)?\]\]')
    for idx, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            titles.append(match.group(1))
            line_map.append(idx)
    return titles, line_map

def remove_old_sections(lines, days=7):
    """Remove sections older than given days.
    Assumes sections start with lines like == YYYY-MM-DD HH:MM UTC ==."""
    new_lines = []
    current_section_date = None
    section_buffer = []

    date_pattern = re.compile(r'^==\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC)\s*==\s*$')
    now = datetime.datetime.utcnow()

    def section_is_recent(section_date_str):
        try:
            section_date = datetime.datetime.strptime(section_date_str, "%Y-%m-%d %H:%M UTC")
        except Exception:
            return True  # If cannot parse, keep section
        age = now - section_date
        return age.days < days

    for line in lines:
        m = date_pattern.match(line)
        if m:
            # New section started: flush previous section if recent
            if current_section_date is None or section_is_recent(current_section_date):
                new_lines.extend(section_buffer)
            # Reset for new section
            current_section_date = m.group(1)
            section_buffer = [line]
        else:
            section_buffer.append(line)
    # Flush last section
    if current_section_date is None or section_is_recent(current_section_date):
        new_lines.extend(section_buffer)
    return new_lines

def run_bot():
    username = os.getenv("BOT_USERNAME")
    password = os.getenv("BOT_PASSWORD")
    page_title = "User:Fixinbot/Updates"

    if not username or not password:
        print("❌ Missing BOT_USERNAME or BOT_PASSWORD environment variables")
        sys.exit(1)

    session = login_and_get_session(username, password)
    text = get_current_page_text(session, page_title)
    if not text.strip():
        print(f"ℹ️ Page {page_title} is empty or not found.")
        return

    lines = text.splitlines()

    # Remove old sections
    lines = remove_old_sections(lines, days=7)

    # Now remove deleted and duplicate pages as before
    titles, line_indices = extract_titles_in_lines(lines)

    if not titles:
        print("ℹ️ No page links found to check.")
        return

    existing_titles = check_pages_exist(session, titles)

    seen = set()
    lines_to_remove = []
    for title, line_idx in zip(titles, line_indices):
        if title not in existing_titles:
            # Mark line for removal: deleted page
            lines_to_remove.append(line_idx)
        elif title in seen:
            # Duplicate page link, mark for removal
            lines_to_remove.append(line_idx)
        else:
            seen.add(title)

    if lines_to_remove:
        # Remove lines marked (in reverse order to keep indexes correct)
        for idx in sorted(lines_to_remove, reverse=True):
            del lines[idx]

        new_text = "\n".join(lines)

        token = get_csrf_token(session)
        r = session.post(API_URL, data={
            'action': 'edit',
            'title': page_title,
            'text': new_text,
            'token': token,
            'format': 'json',
            'bot': True,
            'summary': 'Removed deleted, duplicate, and entries older than 7 days (bot)',
            'assert': 'user',
        })

        result = r.json()
        if 'error' in result:
            err = result['error']
            if err.get('code') == 'blocked':
                print(f"❌ Edit blocked: {err.get('info', '')}")
                sys.exit(1)
            else:
                print(f"❌ Edit error: {err}")
                sys.exit(1)
        elif result.get('edit', {}).get('result') == 'Success':
            print(f"✅ Cleaned and updated page {page_title}")
        else:
            print(f"❌ Unexpected edit response: {result}")
            sys.exit(1)
    else:
        print("✅ No deleted, duplicate, or old entries found.")

if __name__ == "__main__":
    run_bot()
