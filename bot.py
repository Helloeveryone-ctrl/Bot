import os
import re
import requests
import mwparserfromhell
import time
from collections import defaultdict

API_URL = "https://test.wikipedia.org/w/api.php"
USERPAGE_TITLE = "User:Cactusisme/patrolling articles"
HEADERS = {
    'User-Agent': 'CactusBot/1.0 (https://test.wikipedia.org/wiki/User:Cactusisme)'
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
        raise Exception("Login failed!")

    print(f"✅ Logged in as {username}")
    return session

def get_csrf_token(session):
    r = session.get(API_URL, params={
        'action': 'query',
        'meta': 'tokens',
        'format': 'json'
    })
    return r.json()['query']['tokens']['csrftoken']

def get_drafts(session):
    drafts = []
    eicontinue = ""
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
        drafts.extend(r['query']['allpages'])

        if 'continue' in r:
            eicontinue = r['continue']['apcontinue']
        else:
            break
    return drafts

def is_submitted(wikitext):
    code = mwparserfromhell.parse(wikitext)
    for tmpl in code.filter_templates():
        if 'AFC submission' in tmpl.name.strip().lower():
            return True
    return False

def fetch_wikitext(session, title):
    r = session.get(API_URL, params={
        'action': 'query',
        'prop': 'revisions',
        'rvslots': 'main',
        'rvprop': 'content',
        'format': 'json',
        'titles': title
    })

    pages = r['query']['pages']
    for page in pages.values():
        if 'revisions' in page:
            return page['revisions'][0]['slots']['main']['content']
    return ""

def build_sorted_draft_list(session, drafts):
    grouped = defaultdict(list)
    for page in drafts:
        title = page['title']
        short_title = title.replace("Draft:", "")
        first_letter = short_title[0].upper()
        wikitext = fetch_wikitext(session, title)
        status = "(submitted)" if is_submitted(wikitext) else "(unsubmitted)"
        grouped[first_letter].append(f"* [[{title}]] {status}")
        time.sleep(0.5)  # avoid hitting rate limits

    output = []
    for letter in sorted(grouped):
        output.append(f"== {letter} ==")
        output.extend(sorted(grouped[letter], key=lambda x: x.lower()))

    return '\n'.join(output)

def update_userpage(session, content):
    token = get_csrf_token(session)
    r = session.post(API_URL, data={
        'action': 'edit',
        'title': USERPAGE_TITLE,
        'text': content,
        'token': token,
        'summary': 'Bot: Updating list of patrolling articles (Draft namespace)',
        'format': 'json',
        'assert': 'user',
        'bot': True
    })

    if r.json().get('edit', {}).get('result') == 'Success':
        print(f"✅ Updated {USERPAGE_TITLE}")
    else:
        print(f"❌ Failed to update: {r.json()}")

def run_bot():
    username = os.getenv("BOT_USERNAME")
    password = os.getenv("BOT_PASSWORD")

    if not username or not password:
        print("❌ BOT_USERNAME or BOT_PASSWORD not set.")
        return

    session = login_and_get_session(username, password)
    drafts = get_drafts(session)
    print(f"🔍 Found {len(drafts)} draft pages.")
    content = build_sorted_draft_list(session, drafts)
    update_userpage(session, content)

if __name__ == "__main__":
    run_bot()
