import os
import requests
import datetime
import sys
import re

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
    # Wikipedia API limits max titles per request (max 50 for normal users)
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
            # pageid == -1 means missing/deleted
            if int(page_id) > 0:
                existing.add(page['title'])
    return existing

def parse_sections_and_titles(text):
    """Parse sections with == headers and extract list of page titles from bullet points."""
    sections = re.split(r'^(==[^=]+==)\s*$', text, flags=re.MULTILINE)
    # re.split returns list: [before_first_section, header1, content1, header2, content2,...]
    # So group into [(header, content), ...]
    section_pairs = []
    for i in range(1, len(sections), 2):
        header = sections[i].strip()
        content = sections[i+1] if (i+1) < len(sections) else ''
        section_pairs.append((header, content))
    return section_pairs

def clean_titles_from_content(content):
    """Extract all page titles from lines like * [[Page title]]"""
    titles = []
    for line in content.splitlines():
        line = line.strip()
        m = re.match(r'^\*\s*\[\[(.+?)(\|.*)?\]\]', line)
        if m:
            titles.append(m.group(1))
    return titles

def rebuild_section(header, titles):
    lines = [f"* [[{title}]]" for title in sorted(titles)]
    return f"{header}\n" + "\n".join(lines) + "\n"

def save_cleaned_page(session, page_title, sections):
    new_text = ""
    for header, titles in sections:
        new_text += rebuild_section(header, titles) + "\n"
    token = get_csrf_token(session)
    r = session.post(API_URL, data={
        'action': 'edit',
        'title': page_title,
        'text': new_text.strip(),
        'token': token,
        'format': 'json',
        'bot': True,
        'summary': 'Removed deleted and duplicate pages from updates (bot)',
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

    sections = parse_sections_and_titles(text)

    cleaned_sections = []
    for header, content in sections:
        titles = clean_titles_from_content(content)
        if not titles:
            cleaned_sections.append((header, []))
            continue

        existing_titles = check_pages_exist(session, titles)
        # Remove duplicates by converting to set then back to list sorted
        unique_existing = sorted(existing_titles)
        cleaned_sections.append((header, unique_existing))

    save_cleaned_page(session, page_title, cleaned_sections)

if __name__ == "__main__":
    run_bot()
