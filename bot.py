import os
import requests
import mwparserfromhell
import time

API_URL = "https://simple.wikipedia.org/w/api.php"
SAVE_PAGE = "User:Fixinbot/Drafts review"  # The page to save the draft list
HEADERS = {
    'User-Agent': 'DraftListBot/1.0 (https://simple.wikipedia.org/wiki/User:Fixinbot)'
}

def login_and_get_session(username, password):
    session = requests.Session()
    session.headers.update(HEADERS)

    # Get login token
    r1 = session.get(API_URL, params={
        'action': 'query',
        'meta': 'tokens',
        'type': 'login',
        'format': 'json'
    })
    login_token = r1.json()['query']['tokens']['logintoken']

    # Perform login
    r2 = session.post(API_URL, data={
        'action': 'login',
        'lgname': username,
        'lgpassword': password,
        'lgtoken': login_token,
        'format': 'json'
    })
    if r2.json()['login']['result'] != 'Success':
        raise Exception("Login failed!")

    # Confirm logged-in user
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

def fetch_all_drafts(session):
    drafts = []
    apcontinue = None
    while True:
        params = {
            'action': 'query',
            'list': 'allpages',
            'apnamespace': 118,
            'aplimit': 'max',
            'format': 'json'
        }
        if apcontinue:
            params['apcontinue'] = apcontinue

        r = session.get(API_URL, params=params)
        data = r.json()
        drafts.extend([page['title'] for page in data['query']['allpages']])

        if 'continue' in data:
            apcontinue = data['continue']['apcontinue']
        else:
            break
    print(f"📄 Found {len(drafts)} drafts")
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
    pages = r.json()['query']['pages']
    if not pages or 'missing' in pages[0]:
        return False
    content = pages[0].get('revisions', [{}])[0].get('slots', {}).get('main', {}).get('content', '')
    code = mwparserfromhell.parse(content)
    for tmpl in code.filter_templates():
        if tmpl.name.strip().lower() == "afc submission":
            return True
    return False

def generate_draft_list(drafts, session):
    # Group drafts by first letter after "Draft:"
    grouped = {}
    for full_title in drafts:
        title = full_title.replace("Draft:", "", 1)
        first_letter = title[0].upper()
        status = "submitted" if check_if_submitted(session, full_title) else "unsubmitted"
        entry = f"* [[{full_title}]] ({status})"
        grouped.setdefault(first_letter, []).append(entry)
    # Sort letters and entries
    for letter in grouped:
        grouped[letter].sort()
    sorted_letters = sorted(grouped.keys())

    lines = []
    for letter in sorted_letters:
        lines.append(f"=={letter}==")
        lines.extend(grouped[letter])
        lines.append("")  # blank line

    return "\n".join(lines)

def save_page(text, session, token):
    r = session.post(API_URL, data={
        'action': 'edit',
        'title': SAVE_PAGE,
        'text': text,
        'token': token,
        'format': 'json',
        'bot': True,
        'summary': 'Bot: Updating draft list with submission status'
    })
    result = r.json()
    if result.get('edit', {}).get('result') == 'Success':
        print(f"✅ Successfully saved {SAVE_PAGE}")
    else:
        print(f"❌ Failed to save {SAVE_PAGE}: {result}")

def run_bot():
    username = os.getenv("BOT_USERNAME")
    password = os.getenv("BOT_PASSWORD")

    if not username or not password:
        print("Missing BOT_USERNAME or BOT_PASSWORD environment variables.")
        return

    session = login_and_get_session(username, password)
    drafts = fetch_all_drafts(session)
    page_text = generate_draft_list(drafts, session)
    token = get_csrf_token(session)
    save_page(page_text, session, token)

if __name__ == "__main__":
    run_bot()
