import os
import sys
import time
import re
import requests
import mwparserfromhell

API_URL = "https://test.wikipedia.org/w/api.php"

HEADERS = {
    'User-Agent': 'Fixinbot/1.0 (https://test.wikipedia.org/wiki/User:Fixinbot)'
}

EXEMPT_PATTERNS = [
    r'\b\d{1,4}s?\s*(BC|AD)?\b',  # years/decades
    r'\b\d{1,2}(st|nd|rd|th)\s*century\b',
    r'\b\d{1,4}\s+(births|deaths)\b',
    r'\b\d{1,4}s?\s+works\b',
    r'\b\d{1,4}s?\s+(establishments|disestablishments)\b',
    r'(establishments|disestablishments) in .+? by (century|decade)',
    r'\b(establishments|disestablishments) by (country|continent)\b',
    r'\b.*? people\b',
    r'Category:[A-Z][a-z]+(\s\([a-z]+\))?$',
    r'IUCN Red List category'
]

def is_exempt(title):
    for pattern in EXEMPT_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            return True
    return False

def login_and_get_session(username, password):
    session = requests.Session()
    session.headers.update(HEADERS)

    r1 = session.get(API_URL, params={'action': 'query', 'meta': 'tokens', 'type': 'login', 'format': 'json'})
    login_token = r1.json()['query']['tokens']['logintoken']

    r2 = session.post(API_URL, data={
        'action': 'login',
        'lgname': username,
        'lgpassword': password,
        'lgtoken': login_token,
        'format': 'json'
    })

    if r2.json()['login']['result'] != 'Success':
        print("Login failed")
        sys.exit(1)

    return session

def get_csrf_token(session):
    r = session.get(API_URL, params={'action': 'query', 'meta': 'tokens', 'format': 'json'})
    return r.json()['query']['tokens']['csrftoken']

def get_all_category_pages(session, apcontinue=None, limit=50):
    params = {
        'action': 'query',
        'list': 'allpages',
        'apnamespace': 14,
        'aplimit': limit,
        'format': 'json',
    }
    if apcontinue:
        params['apcontinue'] = apcontinue
    r = session.get(API_URL, params=params)
    data = r.json()
    pages = data.get('query', {}).get('allpages', [])
    apcontinue = data.get('continue', {}).get('apcontinue', None)
    return pages, apcontinue

def get_category_members(session, category_title):
    members = []
    cmcontinue = None
    while True:
        params = {
            'action': 'query',
            'list': 'categorymembers',
            'cmtitle': category_title,
            'cmtype': 'page',
            'cmlimit': 'max',
            'format': 'json'
        }
        if cmcontinue:
            params['cmcontinue'] = cmcontinue
        r = session.get(API_URL, params=params)
        data = r.json()
        members += data.get('query', {}).get('categorymembers', [])
        if 'continue' in data:
            cmcontinue = data['continue']['cmcontinue']
        else:
            break
    return members

def get_page_content(session, title):
    r = session.get(API_URL, params={
        'action': 'query',
        'prop': 'revisions',
        'titles': title,
        'rvprop': 'content',
        'format': 'json'
    })
    pages = r.json().get('query', {}).get('pages', {})
    for page in pages.values():
        revs = page.get('revisions', [])
        if revs:
            return revs[0].get('*', '')
    return ''

def is_redirect(session, title):
    r = session.get(API_URL, params={
        'action': 'query',
        'titles': title,
        'format': 'json',
        'redirects': 1
    })
    pages = r.json().get('query', {}).get('pages', {})
    for page_id, page_data in pages.items():
        if 'redirect' in page_data:
            return True
    return False

def save_page(session, title, text, summary):
    token = get_csrf_token(session)
    r = session.post(API_URL, data={
        'action': 'edit',
        'title': title,
        'text': text,
        'token': token,
        'format': 'json',
        'bot': True,
        'summary': summary,
        'assert': 'user',
    })
    result = r.json()
    if result.get('edit', {}).get('result') == 'Success':
        print(f"✅ Edited {title} — {summary}")
        return True
    else:
        print(f"❌ Failed to edit {title}: {result}")
        return False

def process_category_page(session, title):
    if is_redirect(session, title):
        print(f"⏩ Skipping redirect: {title}")
        return

    member_pages = get_category_members(session, title)
    num_pages = len(member_pages)
    content = get_page_content(session, title)
    wikicode = mwparserfromhell.parse(content)
    popcat_templates = [t for t in wikicode.filter_templates() if t.name.strip().lower() == "popcat"]
    has_popcat = bool(popcat_templates)
    changed = False

    if num_pages >= 3:
        if has_popcat:
            for t in popcat_templates:
                wikicode.remove(t)
            changed = True
            summary = "Removing {{popcat}} — 3 or more pages"
    elif num_pages < 3:
        if not has_popcat and not is_exempt(title):
            wikicode.insert(0, "{{popcat}}\n")
            changed = True
            summary = "Adding {{popcat}} — fewer than 3 pages and not exempt"

    if changed:
        save_page(session, title, str(wikicode), summary)
        time.sleep(5)
    else:
        print(f"✔ No change for {title}")

def main():
    username = os.getenv("BOT_USERNAME")
    password = os.getenv("BOT_PASSWORD")
    if not username or not password:
        print("❌ Missing BOT_USERNAME or BOT_PASSWORD")
        sys.exit(1)

    session = login_and_get_session(username, password)

    apcontinue = None
    while True:
        pages, apcontinue = get_all_category_pages(session, apcontinue=apcontinue, limit=50)
        for page in pages:
            title = page['title']
            process_category_page(session, title)
        if not apcontinue:
            break

if __name__ == "__main__":
    main()
