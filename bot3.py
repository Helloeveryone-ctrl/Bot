import os
import requests
import sys
import mwparserfromhell
import time

API_URL = "https://test.wikipedia.org/w/api.php"

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

    if r2.json()['login']['result'] != 'Success':
        print("Login failed")
        sys.exit(1)

    print("Logged in successfully.")
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
        'format': 'json'
    }
    if apcontinue:
        params['apcontinue'] = apcontinue

    r = session.get(API_URL, params=params)
    data = r.json()
    return data.get('query', {}).get('allpages', []), data.get('continue', {}).get('apcontinue', None)

def get_category_member_count(session, category_title):
    cmparams = {
        'action': 'query',
        'list': 'categorymembers',
        'cmtitle': category_title,
        'cmlimit': 1,
        'format': 'json'
    }
    r = session.get(API_URL, params=cmparams)
    return r.json().get('query', {}).get('categorymembers', []), r.json().get('query-continue')

def get_category_page_content(session, title):
    r = session.get(API_URL, params={
        'action': 'query',
        'prop': 'revisions',
        'rvprop': 'content',
        'titles': title,
        'format': 'json'
    })
    pages = r.json().get('query', {}).get('pages', {})
    for page_id in pages:
        return pages[page_id].get('revisions', [{}])[0].get('*', '')
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
    if result.get('edit', {}).get('result') == 'Success':
        print(f"✅ Edited {title}")
    else:
        print(f"❌ Failed to edit {title}: {result}")

def process_category(session, category_title):
    members, _ = get_category_member_count(session, category_title)
    count = len(members)

    if count < 3:
        print(f"Skipping {category_title}, has less than 3 members")
        return

    # Process the category page content
    content = get_category_page_content(session, category_title)
    if not content:
        print(f"⚠️ Couldn't fetch content for {category_title}")
        return

    wikicode = mwparserfromhell.parse(content)
    templates = wikicode.filter_templates()
    changed = False

    for template in templates:
        if template.name.strip().lower() == 'popcat':
            wikicode.remove(template)
            changed = True
            print(f"Removing {{popcat}} from {category_title}")
            break

    if changed:
        save_page(session, category_title, str(wikicode), "Removed {{popcat}} (3 or more pages in category)")
        time.sleep(5)  # Delay to avoid hitting the rate limit

def main():
    username = os.getenv("BOT_USERNAME")
    password = os.getenv("BOT_PASSWORD")

    if not username or not password:
        print("❌ Missing BOT_USERNAME or BOT_PASSWORD")
        sys.exit(1)

    session = login_and_get_session(username, password)

    apcontinue = None
    while True:
        pages, apcontinue = get_all_category_pages(session, apcontinue=apcontinue)
        if not pages:
            break

        for page in pages:
            category_title = page['title']
            print(f"Checking {category_title}...")
            process_category(session, category_title)

        if not apcontinue:
            break

if __name__ == "__main__":
    main()
