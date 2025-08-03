import os
import requests
import mwparserfromhell
import time
import re
from collections import defaultdict

API_URL = "https://test.wikipedia.org/w/api.php"
HEADERS = {
    'User-Agent': 'Fixinbot/1.0 (https://test.wikipedia.org/wiki/User:Fixinbot)'
}

def login_and_get_session():
    username = "Cactusisme@Fixinbot"
    password = "qft8e10vj9g93ltn1adee1u00jf3e74c"

    session = requests.Session()
    session.headers.update(HEADERS)

    # Step 1: Get login token
    r1 = session.get(API_URL, params={
        'action': 'query',
        'meta': 'tokens',
        'type': 'login',
        'format': 'json'
    })
    login_token = r1.json()['query']['tokens']['logintoken']

    # Step 2: Login
    r2 = session.post(API_URL, data={
        'action': 'login',
        'lgname': username,
        'lgpassword': password,
        'lgtoken': login_token,
        'format': 'json'
    })

    if r2.json().get('login', {}).get('result') != 'Success':
        raise Exception(f"Login failed: {r2.json()}")

    # Step 3: Confirm login
    r3 = session.get(API_URL, params={
        'action': 'query',
        'meta': 'userinfo',
        'format': 'json'
    })
    logged_in_user = r3.json()['query']['userinfo']['name']
    print(f"✅ Logged in as {logged_in_user}")

    return session

def get_csrf_token(session):
    r = session.get(API_URL, params={
        'action': 'query',
        'meta': 'tokens',
        'format': 'json'
    })
    return r.json()['query']['tokens']['csrftoken']

def fetch_drafts(session):
    drafts = []
    eicontinue = ''

    while True:
        params = {
            'action': 'query',
            'list': 'allpages',
            'apnamespace': 118,
            'aplimit': 'max',
            'format': 'json'
        }
        if eicontinue:
            params['apcontinue'] = eicontinue

        r = session.get(API_URL, params=params).json()
        pages = r['query']['allpages']
        drafts.extend(pages)

        if 'continue' in r:
            eicontinue = r['continue']['apcontinue']
        else:
            break

    return drafts

def check_if_submitted(session, title):
    r = session.get(API_URL, params={
        'action': 'query',
        'prop': 'revisions',
        'titles': title,
        'rvslots': 'main',
        'rvprop': 'content',
        'formatversion': 2,
        'format': 'json'
    })
    page = r['query']['pages'][0]
    if 'revisions' not in page:
        return False
    text = page['revisions'][0]['slots']['main']['content']
    return '{{Afc submission' in text

def generate_draft_list(drafts, session):
    groups = defaultdict(list)

    for page in drafts:
        title = page['title']
        pagename = title.replace("Draft:", "")
        first_letter = pagename[0].upper()
        status = "submitted" if check_if_submitted(session, title) else "unsubmitted"
        groups[first_letter].append(f"*[[{title}]] ({status})")

    output = []
    for letter in sorted(groups):
        output.append(f"=={letter}==")
        output.extend(sorted(groups[letter], key=str.casefold))

    return '\n'.join(output)

def save_to_page(session, text, title):
    token = get_csrf_token(session)
    r = session.post(API_URL, data={
        'action': 'edit',
        'title': title,
        'text': text,
        'token': token,
        'summary': 'Bot: Updating draft list',
        'format': 'json',
        'assert': 'user',
        'bot': True
    })
    result = r.json()
    if result.get('edit', {}).get('result') == 'Success':
        print(f"✅ Successfully updated: {title}")
    else:
        print(f"❌ Failed to update: {result}")

def run_bot():
    session = login_and_get_session()
    drafts = fetch_drafts(session)
    print(f"📄 Found {len(drafts)} drafts")
    page_text = generate_draft_list(drafts, session)
    save_to_page(session, page_text, "User:Cactusisme/patrolling articles")

if __name__ == "__main__":
    run_bot()
