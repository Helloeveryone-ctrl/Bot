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


def get_active_admins(session):
    """Fetch all admins and their activity timestamps."""
    admins = []
    aufrom = None

    while True:
        params = {
            'action': 'query',
            'list': 'allusers',
            'augroup': 'sysop',
            'aulimit': 'max',
            'format': 'json'
        }
        if aufrom:
            params['aufrom'] = aufrom

        r = session.get(API_URL, params=params)
        data = r.json()
        users = data.get('query', {}).get('allusers', [])

        for user in users:
            username = user['name']

            # Last edit
            r2 = session.get(API_URL, params={
                'action': 'query',
                'list': 'usercontribs',
                'ucuser': username,
                'uclimit': 1,
                'ucprop': 'timestamp',
                'format': 'json'
            })
            contribs = r2.json().get('query', {}).get('usercontribs', [])
            last_edit = contribs[0]['timestamp'] if contribs else None

            # Last log
            r3 = session.get(API_URL, params={
                'action': 'query',
                'list': 'logevents',
                'leuser': username,
                'lelimit': 1,
                'format': 'json'
            })
            logs = r3.json().get('query', {}).get('logevents', [])
            last_log = logs[0]['timestamp'] if logs else None

            # Activity score
            last_activity = None
            if last_edit and last_log:
                last_activity = max(last_edit, last_log)
            elif last_edit:
                last_activity = last_edit
            elif last_log:
                last_activity = last_log

            admins.append({
                'username': username,
                'last_edit': last_edit or "—",
                'last_log': last_log or "—",
                'last_activity': last_activity
            })

        if 'continue' in data:
            aufrom = data['continue']['aufrom']
        else:
            break

    # Sort by last_activity descending
    admins.sort(key=lambda x: x['last_activity'] or "0000", reverse=True)
    return admins


def build_table(admins):
    """Builds the wikitable text."""
    lines = [
        '{| class="wikitable sortable"',
        '! Rank',
        '! Username',
        '! Last edit',
        '! Last logged action'
    ]
    for i, admin in enumerate(admins, start=1):
        lines.append('|-')
        lines.append(f'| {i}')
        lines.append(f'| [[User:{admin["username"]}|{admin["username"]}]]')
        lines.append(f'| {admin["last_edit"]}')
        lines.append(f'| {admin["last_log"]}')
    lines.append('|}')
    return "\n".join(lines)


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


def get_csrf_token(session):
    r = session.get(API_URL, params={
        'action': 'query',
        'meta': 'tokens',
        'format': 'json'
    })
    return r.json()['query']['tokens']['csrftoken']


def save_to_page(session, page_title, admins):
    new_table = build_table(admins)
    current_text = get_current_page_text(session, page_title)

    # Replace existing table or create new one under "== Active admins =="
    if re.search(r'\{\| class="wikitable sortable".*?\|\}', current_text, re.S):
        new_text = re.sub(r'\{\| class="wikitable sortable".*?\|\}', new_table, current_text, flags=re.S)
    else:
        new_text = current_text.strip() + "\n\n== Active admins ==\n" + new_table

    token = get_csrf_token(session)

    r = session.post(API_URL, data={
        'action': 'edit',
        'title': page_title,
        'text': new_text,
        'token': token,
        'format': 'json',
        'bot': True,
        'summary': 'Updating active admins table (bot)',
        'assert': 'user',
    })

    result = r.json()
    if 'error' in result:
        print(f"❌ Edit error: {result['error']}")
        sys.exit(1)
    elif result.get('edit', {}).get('result') == 'Success':
        print(f"✅ Updated page {page_title}")
    else:
        print(f"❌ Unexpected response: {result}")
        sys.exit(1)


def run_bot():
    username = os.getenv("BOT_USERNAME")
    password = os.getenv("BOT_PASSWORD")
    save_page = "User:Fixinbot/Updates"

    if not username or not password:
        print("❌ Missing BOT_USERNAME or BOT_PASSWORD environment variables")
        sys.exit(1)

    session = login_and_get_session(username, password)
    admins = get_active_admins(session)

    if admins:
        save_to_page(session, save_page, admins)
    else:
        print("ℹ️ No admins found.")


if __name__ == "__main__":
    run_bot()
