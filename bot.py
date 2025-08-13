import os
import requests
import datetime
import sys

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


def get_recent_pages(session, minutes=60):
    now = datetime.datetime.utcnow()
    start = now - datetime.timedelta(minutes=minutes)
    start_iso = start.strftime('%Y-%m-%dT%H:%M:%SZ')

    titles = []
    rccontinue = None

    while True:
        params = {
            'action': 'query',
            'list': 'recentchanges',
            'rcstart': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'rcend': start_iso,
            'rcdir': 'older',
            'rcnamespace': 0,
            'rctype': 'new',
            'rclimit': 'max',
            'format': 'json'
        }
        if rccontinue:
            params['rccontinue'] = rccontinue

        r = session.get(API_URL, params=params)
        data = r.json()
        changes = data.get('query', {}).get('recentchanges', [])

        for change in changes:
            titles.append(change['title'])

        if 'continue' in data:
            rccontinue = data['continue']['rccontinue']
        else:
            break

    return sorted(set(titles))


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
        'rvprop': 'content',
        'format': 'json'
    })
    pages = r.json()['query']['pages']
    for page_id in pages:
        return pages[page_id].get('revisions', [{}])[0].get('*', '')
    return ''


def save_to_page(session, page_title, lines):
    now = datetime.datetime.utcnow()
    timestamp = now.strftime('%Y-%m-%d %H:%M UTC')
    section_header = f"== {timestamp} ==\n"

    # Build wikitext table
    table_lines = [
        '{| class="wikitable sortable"',
        '! #',
        '! Page'
    ]
    for i, title in enumerate(lines, start=1):
        table_lines.append('|-')
        table_lines.append(f'| {i}')
        table_lines.append(f'| [[{title}]]')
    table_lines.append('|}')

    section_content = "\n".join(table_lines) + "\n\n"
    new_section = section_header + section_content

    existing_text = get_current_page_text(session, page_title)
    new_text = new_section + existing_text

    token = get_csrf_token(session)

    r = session.post(API_URL, data={
        'action': 'edit',
        'title': page_title,
        'text': new_text,
        'token': token,
        'format': 'json',
        'bot': True,
        'summary': f'Added table for {timestamp} (bot)',
        'assert': 'user',
    })

    result = r.json()

    if 'error' in result:
        err = result['error']
        if err.get('code') == 'blocked':
            print(f"❌ Edit blocked: {err.get('info', '')}")
            sys.exit(1)
        else:
            print(f"❌ Edit error: {err}")
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

    titles = get_recent_pages(session, minutes=60)

    if titles:
        print(f"📄 Found {len(titles)} new pages in the past hour")
        save_to_page(session, save_page, titles)
    else:
        print("ℹ️ No new pages found.")


if __name__ == "__main__":
    run_bot()
