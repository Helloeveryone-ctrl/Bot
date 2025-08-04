import os
import requests
import time

API_URL = "https://en.wikipedia.org/w/api.php"

HEADERS = {
    'User-Agent': 'Fixinbot/1.0 (https://en.wikipedia.org/wiki/User:Fixinbot)'
}

def login_and_get_session(username, password):
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

    # Step 2: Post login request
    r2 = session.post(API_URL, data={
        'action': 'login',
        'lgname': username,
        'lgpassword': password,
        'lgtoken': login_token,
        'format': 'json'
    })

    if r2.json()['login']['result'] != 'Success':
        raise Exception(f"Login failed! Response: {r2.json()}")

    # Step 3: Confirm login by fetching user info
    r3 = session.get(API_URL, params={
        'action': 'query',
        'meta': 'userinfo',
        'format': 'json'
    })
    logged_in_user = r3.json()['query']['userinfo']['name']
    print(f"✅ Logged in as {logged_in_user}")

    return session

def fetch_drafts(session):
    drafts = []
    apcontinue = None
    while True:
        params = {
            'action': 'query',
            'list': 'allpages',
            'apnamespace': 118,
            'aplimit': 'max',
            'format': 'json',
        }
        if apcontinue:
            params['apcontinue'] = apcontinue

        r = session.get(API_URL, params=params)
        data = r.json()

        pages = data['query']['allpages']
        for p in pages:
            drafts.append(p['title'])

        if 'continue' in data:
            apcontinue = data['continue']['apcontinue']
            time.sleep(0.5)
        else:
            break

    print(f"📄 Found {len(drafts)} drafts")
    return drafts

def generate_draft_list(drafts):
    grouped = {}
    for title in drafts:
        if title.startswith("Draft:"):
            page_name = title[6:]
        else:
            page_name = title
        if not page_name:
            continue
        first_letter = page_name[0].upper()
        grouped.setdefault(first_letter, []).append(title)

    output_lines = []
    for letter in sorted(grouped.keys()):
        output_lines.append(f"=={letter}==")
        for title in sorted(grouped[letter]):
            output_lines.append(f"* [[{title}]]")
        output_lines.append("")  # blank line after each section

    return "\n".join(output_lines)

def save_to_page(session, page_title, text):
    token = get_csrf_token(session)
    r = session.post(API_URL, data={
        'action': 'edit',
        'title': page_title,
        'text': text,
        'token': token,
        'format': 'json',
        'bot': True,
        'summary': 'Updating page (bot)',
        'assert': 'user',
    })
    result = r.json()
    if result.get('edit', {}).get('result') == 'Success':
        print(f"✅ Updated page {page_title}")
    else:
        print(f"❌ Failed to update page {page_title}: {result}")

def get_csrf_token(session):
    r = session.get(API_URL, params={
        'action': 'query',
        'meta': 'tokens',
        'format': 'json'
    })
    return r.json()['query']['tokens']['csrftoken']

def run_bot():
    username = os.getenv("BOT_USERNAME")
    password = os.getenv("BOT_PASSWORD")
    save_page = "User:Fixinbot/AFC helper"

    if not username or not password:
        print("Missing BOT_USERNAME or BOT_PASSWORD environment variables")
        return

    session = login_and_get_session(username, password)
    drafts = fetch_drafts(session)
    draft_list_text = generate_draft_list(drafts)
    save_to_page(session, save_page, draft_list_text)

if __name__ == "__main__":
    run_bot()
