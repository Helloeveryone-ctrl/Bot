import os
import requests
import datetime

API_URL = "https://en.wikipedia.org/w/api.php"

HEADERS = {
    'User-Agent': 'Fixinbot/1.0 (https://en.wikipedia.org/wiki/User:Fixinbot)'
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

    # Log in
    r2 = session.post(API_URL, data={
        'action': 'login',
        'lgname': username,
        'lgpassword': password,
        'lgtoken': login_token,
        'format': 'json'
    })

    if r2.json()['login']['result'] != 'Success':
        raise Exception(f"Login failed! Response: {r2.json()}")

    # Confirm login
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
            'rcnamespace': 0,  # Only mainspace; use 118 for Draft
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


def save_to_page(session, page_title, lines):
    text = "== Pages created in the past hour ==\n" + "\n".join(f"* [[{title}]]" for title in lines)

    token = get_csrf_token(session)
    r = session.post(API_URL, data={
        'action': 'edit',
        'title': page_title,
        'text': text,
        'token': token,
        'format': 'json',
        'bot': True,
        'summary': 'Updating recent page creations (bot)',
        'assert': 'user',
    })
    result = r.json()
    if result.get('edit', {}).get('result') == 'Success':
        print(f"✅ Updated page {page_title}")
    else:
        print(f"❌ Failed to update page {page_title}: {result}")


def run_bot():
    username = os.getenv("BOT_USERNAME")
    password = os.getenv("BOT_PASSWORD")
    save_page = "User:Fixinbot/Updates"

    if not username or not password:
        print("❌ Missing BOT_USERNAME or BOT_PASSWORD environment variables")
        return

    session = login_and_get_session(username, password)
    titles = get_recent_pages(session, minutes=60)

    print(f"📄 Found {len(titles)} new pages in the past hour")
    save_to_page(session, save_page, titles)


if __name__ == "__main__":
    run_bot()
