import os
import re
import requests
import mwparserfromhell
import time

API_URL = "https://simple.wikipedia.org/w/api.php"

HEADERS = {
    'User-Agent': 'Fixinbot/1.0 (https://simple.wikipedia.org/wiki/User:Fixinbot)'
}

def login_and_get_session(username, password):
    session = requests.Session()
    session.headers.update(HEADERS)

    # Step 1: get login token
    r1 = session.get(API_URL, params={
        'action': 'query',
        'meta': 'tokens',
        'type': 'login',
        'format': 'json'
    })
    login_token = r1.json()['query']['tokens']['logintoken']

    # Step 2: clientlogin with username, password, token
    r2 = session.post(API_URL, data={
        'action': 'clientlogin',
        'username': username,
        'password': password,
        'loginreturnurl': 'https://simple.wikipedia.org',
        'logintoken': login_token,
        'format': 'json'
    })

    print("Login response:", r2.json())

    clientlogin = r2.json().get('clientlogin', {})
    if clientlogin.get('status') != 'PASS':
        raise Exception(f"Login failed! Reason: {clientlogin.get('message', 'unknown')}")

    print(f"✅ Logged in as {username}")
    return session

def get_csrf_token(session):
    r = session.get(API_URL, params={
        'action': 'query',
        'meta': 'tokens',
        'format': 'json'
    })
    return r.json()['query']['tokens']['csrftoken']

def fetch_all_drafts(session):
    drafts = []
    cont = ''
    while True:
        params = {
            'action': 'query',
            'list': 'allpages',
            'apprefix': 'Draft:',
            'aplimit': 'max',
            'format': 'json'
        }
        if cont:
            params['apcontinue'] = cont
        r = session.get(API_URL, params=params).json()
        pages = r['query']['allpages']
        drafts.extend(pages)
        if 'continue' in r:
            cont = r['continue']['apcontinue']
        else:
            break
    return drafts

def check_if_submitted(session, title):
    # Check if the page contains {{afc submission}}
    r = session.get(API_URL, params={
        'action': 'parse',
        'page': title,
        'prop': 'wikitext',
        'format': 'json'
    })
    # parse response JSON
    parse = r.json().get('parse')
    if not parse:
        return False
    wikitext = parse.get('wikitext', {}).get('*', '')
    return '{{afc submission' in wikitext.lower()

def generate_draft_list(drafts, session):
    # Group drafts alphabetically by first letter after 'Draft:'
    grouped = {}
    for page in drafts:
        title = page['title']
        # strip "Draft:" prefix
        base_title = title[6:]
        first_letter = base_title[0].upper()
        status = "submitted" if check_if_submitted(session, title) else "unsubmitted"
        grouped.setdefault(first_letter, []).append((base_title, status))

    # Sort keys and draft titles
    output = []
    for letter in sorted(grouped.keys()):
        output.append(f"=={letter}==")
        # sort pages alphabetically
        for (title, status) in sorted(grouped[letter]):
            output.append(f"* [[{title}]] ({status})")
        output.append("")  # blank line between groups

    return "\n".join(output)

def edit_draft_review_page(text, session, csrf_token, username):
    page_title = f"User:{username}/Drafts review"
    r = session.post(API_URL, data={
        'action': 'edit',
        'title': page_title,
        'text': text,
        'token': csrf_token,
        'summary': 'Bot: Updated drafts list with submission status',
        'format': 'json',
        'bot': True,
        'assert': 'user'
    })
    result = r.json()
    if 'edit' in result and result['edit']['result'] == 'Success':
        print(f"✅ Successfully updated {page_title}")
    else:
        print(f"❌ Failed to update {page_title}: {result}")

def run_bot():
    username = os.getenv("BOT_USERNAME")
    password = os.getenv("BOT_PASSWORD")

    if not username or not password:
        print("Missing BOT_USERNAME or BOT_PASSWORD environment variables.")
        return

    session = login_and_get_session(username, password)

    drafts = fetch_all_drafts(session)
    print(f"📄 Found {len(drafts)} drafts")

    csrf_token = get_csrf_token(session)
    page_text = generate_draft_list(drafts, session)

    edit_draft_review_page(page_text, session, csrf_token, username)

if __name__ == "__main__":
    run_bot()
