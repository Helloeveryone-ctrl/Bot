import os
import requests
import datetime
import sys
import re

API_URL = "https://en.wikipedia.org/w/api.php"

HEADERS = {
    'User-Agent': 'Fixinbot/2.0 (https://en.wikipedia.org/wiki/User:Fixinbot)'
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

    # Login
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

    print(f"✅ Logged in as {username}")
    return session


def get_admins(session):
    """Fetch all sysops (admins)."""
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
        admins.extend([u['name'] for u in users])

        if 'continue' in data:
            aufrom = data['continue']['aufrom']
        else:
            break

    return admins


def get_last_activities(session, admins):
    """Fetch last edit and log for all admins in batches."""
    batch_size = 50
    results = {}

    for i in range(0, len(admins), batch_size):
        chunk = admins[i:i+batch_size]
        userlist = "|".join(chunk)

        # Contributions batch
        r1 = session.get(API_URL, params={
            'action': 'query',
            'list': 'usercontribs',
            'ucuser': userlist,
            'uclimit': 1,
            'ucprop': 'timestamp|user',
            'format': 'json'
        })
        for c in r1.json().get('query', {}).get('usercontribs', []):
            results.setdefault(c['user'], {})['last_edit'] = c['timestamp']

        # Logs batch
        r2 = session.get(API_URL, params={
            'action': 'query',
            'list': 'logevents',
            'leuser': userlist,
            'lelimit': 1,
            'format': 'json'
        })
        for l in r2.json().get('query', {}).get('logevents', []):
            results.setdefault(l['user'], {})['last_log'] = l['timestamp']

    # Normalize results
    output = []
    for user in admins:
        last_edit = results.get(user, {}).get('last_edit', "—")
        last_log = results.get(user, {}).get('last_log', "—")

        # pick whichever timestamp is newer
        if last_edit != "—" and last_log != "—":
            last_activity = max(last_edit, last_log)
        elif last_edit != "—":
            last_activity = last_edit
        elif last_log != "—":
            last_activity = last_log
        else:
            last_activity = None

        output.append({
            "username": user,
            "last_edit": last_edit,
            "last_log": last_log,
            "last_activity": last_activity
        })

    # Sort by recency (most active first)
    output.sort(key=lambda x: x['last_activity'] or "0000", reverse=True)
    return output


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
        'rvslots': 'main',
        'rvprop': 'content',
        'format': 'json'
    })
    pages = r.json()['query']['pages']
    for page_id in pages:
        return pages[page_id].get('revisions', [{}])[0].get('slots', {}).get('main', {}).get('*', '')
    return ''


def save_to_page(session, page_title, admins_data):
    # Build wikitable
    table_lines = [
        '{| class="wikitable sortable"',
        '! Rank',
        '! Username',
        '! Last edit',
        '! Last log'
    ]
    for i, admin in enumerate(admins_data, start=1):
        table_lines.append('|-')
        table_lines.append(f'| {i}')
        table_lines.append(f'| [[User:{admin["username"]}|{admin["username"]}]]')
        table_lines.append(f'| {admin["last_edit"]}')
        table_lines.append(f'| {admin["last_log"]}')
    table_lines.append('|}')

    new_table = "\n".join(table_lines)

    current_text = get_current_page_text(session, page_title)

    if re.search(r'\{\| class="wikitable sortable".*?\|\}', current_text, re.S):
        # Replace existing table
        new_text = re.sub(r'\{\| class="wikitable sortable".*?\|\}', new_table, current_text, flags=re.S)
    else:
        # If no table exists, append at bottom
        new_text = current_text + "\n\n" + new_table

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
        print(f"❌ Edit error: {result}")
        sys.exit(1)
    elif result.get('edit', {}).get('result') == 'Success':
        print(f"✅ Updated page {page_title}")
    else:
        print(f"❌ Unexpected edit response: {result}")
        sys.exit(1)


def run_bot():
    username = os.getenv("BOT_USERNAME")
    password = os.getenv("BOT_PASSWORD")
    save_page = "User:Fixinbot/Updates"

    if not username or not password:
        print("❌ Missing BOT_USERNAME or BOT_PASSWORD environment variables")
        sys.exit(1)

    session = login_and_get_session(username, password)
    admins = get_admins(session)
    print(f"👥 Found {len(admins)} admins")

    admins_data = get_last_activities(session, admins)
    save_to_page(session, save_page, admins_data)


if __name__ == "__main__":
    run_bot()
