import os
import time
import sys
import requests
import mwparserfromhell

API_URL = "https://test.wikipedia.org/w/api.php"
HEADERS = {
    'User-Agent': 'Fixinbot/1.0 (https://test.wikipedia.org/wiki/User:Fixinbot)'
}

def login_and_get_session(username, password):
    session = requests.Session()
    session.headers.update(HEADERS)

    r1 = session.get(API_URL, params={
        'action': 'query', 'meta': 'tokens', 'type': 'login', 'format': 'json'
    })
    login_token = r1.json()['query']['tokens']['logintoken']

    r2 = session.post(API_URL, data={
        'action': 'login', 'lgname': username, 'lgpassword': password,
        'lgtoken': login_token, 'format': 'json'
    })

    if r2.json()['login']['result'] != 'Success':
        print("❌ Login failed.")
        sys.exit(1)

    return session

def get_csrf_token(session):
    r = session.get(API_URL, params={
        'action': 'query', 'meta': 'tokens', 'format': 'json'
    })
    return r.json()['query']['tokens']['csrftoken']

def get_all_category_pages(session, apcontinue=None, limit=50):
    params = {
        'action': 'query',
        'list': 'allpages',
        'apnamespace': 14,
        'aplimit': limit,
        'format': 'json',
    }
    if apcontinue:
        params['apcontinue'] = apcontinue

    r = session.get(API_URL, params=params)
    data = r.json()
    pages = data.get('query', {}).get('allpages', [])
    next_continue = data.get('continue', {}).get('apcontinue', None)
    return pages, next_continue

def get_category_member_count(session, category_title):
    total = 0
    cmcontinue = None

    while True:
        params = {
            'action': 'query',
            'list': 'categorymembers',
            'cmtitle': category_title,
            'cmlimit': 'max',
            'format': 'json'
        }
        if cmcontinue:
            params['cmcontinue'] = cmcontinue

        r = session.get(API_URL, params=params)
        if not r.content:
            return 0
        data = r.json()
        total += len(data.get('query', {}).get('categorymembers', []))

        if 'continue' in data:
            cmcontinue = data['continue']['cmcontinue']
        else:
            break

    return total

def get_page_content(session, title):
    r = session.get(API_URL, params={
        'action': 'query',
        'prop': 'revisions',
        'titles': title,
        'rvprop': 'content',
        'format': 'json'
    })
    pages = r.json().get('query', {}).get('pages', {})
    for page in pages.values():
        return page.get('revisions', [{}])[0].get('*', '')
    return ''

def save_page(session, title, text, summary):
    token = get_csrf_token(session)
    r = session.post(API_URL, data={
        'action': 'edit',
        'title': title,
        'text': text,
        'token': token,
        'format': 'json',
        'bot': True,
        'summary': summary,
        'assert': 'user'
    })

    if 'error' in r.json():
        print(f"❌ Edit error on {title}: {r.json()['error']}")
    elif r.json().get('edit', {}).get('result') == 'Success':
        print(f"✅ Edited {title}")
    else:
        print(f"❌ Unknown edit failure on {title}")

def process_category(session, title):
    count = get_category_member_count(session, title)
    content = get_page_content(session, title)
    if not content:
        print(f"⚠️ Could not get content for {title}")
        return

    code = mwparserfromhell.parse(content)
    has_popcat = any(tpl.name.strip().lower() == "popcat" for tpl in code.filter_templates())
    changed = False

    if count >= 3:
        # Remove popcat if present
        for tpl in code.filter_templates():
            if tpl.name.strip().lower() == "popcat":
                code.remove(tpl)
                changed = True
        if changed:
            save_page(session, title, str(code), "Removing {{popcat}} — category has 3 or more members")
            time.sleep(5)
        else:
            print(f"🔍 {title} has 3+ members, no {{popcat}} to remove.")

    elif count < 3:
        # Add popcat if missing
        if not has_popcat:
            code.insert(0, "{{popcat}}\n")
            changed = True
            save_page(session, title, str(code), "Adding {{popcat}} — category has fewer than 3 members")
            time.sleep(5)
        else:
            print(f"ℹ️ {title} already has {{popcat}}, and <3 members.")

def main():
    username = os.getenv("BOT_USERNAME")
    password = os.getenv("BOT_PASSWORD")
    if not username or not password:
        print("❌ BOT_USERNAME or BOT_PASSWORD not set.")
        sys.exit(1)

    session = login_and_get_session(username, password)
    cont = None

    while True:
        pages, cont = get_all_category_pages(session, apcontinue=cont, limit=50)
        if not pages:
            break

        for page in pages:
            title = page['title']
            print(f"🔎 Checking: {title}")
            process_category(session, title)

        if not cont:
            break

if __name__ == "__main__":
    main()
