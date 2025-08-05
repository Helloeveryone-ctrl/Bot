import os
import requests
import sys
import mwparserfromhell
import datetime

API_URL = "https://test.wikipedia.org/w/api.php"  # Change if needed

HEADERS = {
    'User-Agent': 'Fixinbot/1.0 (https://test.wikipedia.org/wiki/User:Fixinbot)'
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

def get_category_page_categories(session, title):
    params = {
        'action': 'query',
        'prop': 'categories',
        'titles': title,
        'cllimit': 'max',
        'format': 'json'
    }
    r = session.get(API_URL, params=params)
    pages = r.json().get('query', {}).get('pages', {})
    for pageid in pages:
        cats = pages[pageid].get('categories', [])
        return [cat['title'] for cat in cats]
    return []

def get_page_content(session, title):
    params = {
        'action': 'query',
        'prop': 'revisions',
        'titles': title,
        'rvprop': 'content',
        'format': 'json'
    }
    r = session.get(API_URL, params=params)
    pages = r.json().get('query', {}).get('pages', {})
    for pageid in pages:
        revs = pages[pageid].get('revisions', [])
        if revs:
            return revs[0].get('*', '')
    return ''

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
    if 'error' in result:
        print(f"❌ Edit error on {title}: {result['error']}")
        return False
    if result.get('edit', {}).get('result') == 'Success':
        print(f"✅ Edited {title}")
        return True
    print(f"❌ Unexpected edit response on {title}: {result}")
    return False

def log_edit(session, category_title, action):
    log_page = "User:Fixinbot/Log"
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    new_log_line = f"* {timestamp}: Edited [[{category_title}]] — {action}\n"

    current_log = get_page_content(session, log_page)
    new_text = new_log_line + (current_log if current_log else '')

    summary = f"Log edit: {action} on {category_title}"
    save_page(session, log_page, new_text, summary)

def process_category_page(session, title):
    categories = get_category_page_categories(session, title)
    cat_count = len(categories)

    content = get_page_content(session, title)
    if content == '':
        print(f"⚠️ Page {title} content empty or missing.")
        return

    wikicode = mwparserfromhell.parse(content)
    popcat_templates = [t for t in wikicode.filter_templates() if t.name.strip().lower() == 'popcat']

    changed = False
    if cat_count >= 3:
        # Remove {{popcat}} if present
        if popcat_templates:
            for t in popcat_templates:
                wikicode.remove(t)
            changed = True
            summary = "Removed {{popcat}} (category has 3 or more categories)"
            action = "Removed {{popcat}}"
    else:
        # Add {{popcat}} if missing
        if not popcat_templates:
            wikicode.insert(0, "{{popcat}}\n")
            changed = True
            summary = "Added {{popcat}} (category has fewer than 3 categories)"
            action = "Added {{popcat}}"

    if changed:
        if save_page(session, title, str(wikicode), summary):
            log_edit(session, title, action)
    else:
        print(f"No change needed for {title}")

def main():
    username = os.getenv("BOT_USERNAME")
    password = os.getenv("BOT_PASSWORD")
    if not username or not password:
        print("❌ Missing BOT_USERNAME or BOT_PASSWORD environment variables")
        sys.exit(1)

    session = login_and_get_session(username, password)

    apcontinue = None
    while True:
        pages, apcontinue = get_all_category_pages(session, apcontinue=apcontinue, limit=50)
        if not pages:
            print("No category pages found.")
            break

        for page in pages:
            title = page['title']
            print(f"Processing category page: {title}")
            process_category_page(session, title)

        if not apcontinue:
            print("Finished processing all category pages.")
            break

if __name__ == "__main__":
    main()
