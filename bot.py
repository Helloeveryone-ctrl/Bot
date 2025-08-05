import os
import requests
import datetime
import sys

API_URL = "https://en.wikipedia.org/w/api.php"

HEADERS = {
    'User-Agent': 'Fixinbot/1.0 (https://en.wikipedia.org/wiki/User:Fixinbot)'
}

MAX_PAGE_SIZE = 25000  # bytes


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
    section_content = "\n".join(f"* [[{title}]]" for title in lines)

    new_section = f"{section_header}{section_content}\n\n"

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
        'summary': f'Added section for {timestamp} (bot)',
        'assert': 'user',
    })

    result = r.json()

    if 'error' in result:
        err = result['error']
        if err.get('code') == 'blocked':
            print(f"❌ Edit blocked: {err.get('info', '')}")
            print("💡 IP blocked by Wikimedia. Exiting for GitHub Actions to retry.")
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
    base_page = "User:Fixinbot/Updates"

    if not username or not password:
        print("❌ Missing BOT_USERNAME or BOT_PASSWORD environment variables")
        sys.exit(1)

    session = login_and_get_session(username, password)

    titles = get_recent_pages(session, minutes=60)

    if not titles:
        print("ℹ️ No new pages found.")
        return

    print(f"📄 Found {len(titles)} new pages in the past hour")

    now = datetime.datetime.utcnow()
    timestamp = now.strftime('%Y-%m-%d %H:%M UTC')
    section_header = f"== {timestamp} ==\n"
    section_content = "\n".join(f"* [[{title}]]" for title in titles)
    new_section = f"{section_header}{section_content}\n\n"

    # Try base page and increment page number if size limit exceeded
    for i in range(1, 100):  # max 99 pages max, adjust if needed
        if i == 1:
            page_title = base_page
        else:
            page_title = f"{base_page} {i}"

        existing_text = get_current_page_text(session, page_title)
        combined_text = new_section + existing_text

        # Check byte size of combined text
        if len(combined_text.encode('utf-8')) <= MAX_PAGE_SIZE:
            save_to_page(session, page_title, titles)
            break
    else:
        print(f"❌ Could not save: all pages exceeded {MAX_PAGE_SIZE} bytes limit.")


if __name__ == "__main__":
    run_bot()
