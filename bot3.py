import os
import sys
import time
import re
import requests
import mwparserfromhell

API_URL = "https://test.wikipedia.org/w/api.php"

HEADERS = {
    'User-Agent': 'Fixinbot/1.1 (https://test.wikipedia.org/wiki/User:Fixinbot)'
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
        print("Login failed")
        sys.exit(1)

    return session

def get_csrf_token(session):
    r = session.get(API_URL, params={
        'action': 'query',
        'meta': 'tokens',
        'format': 'json'
    })
    return r.json()['query']['tokens']['csrftoken']

def get_category_members(session, category_title, cmtype='page'):
    members = []
    cmcontinue = None
    while True:
        params = {
            'action': 'query',
            'list': 'categorymembers',
            'cmtitle': category_title,
            'cmnamespace': 0 if cmtype == 'page' else 14,
            'cmtype': cmtype,
            'cmlimit': 'max',
            'format': 'json'
        }
        if cmcontinue:
            params['cmcontinue'] = cmcontinue
        r = session.get(API_URL, params=params)
        data = r.json()
        members += data.get('query', {}).get('categorymembers', [])
        if 'continue' in data:
            cmcontinue = data['continue']['cmcontinue']
        else:
            break
    return members

def get_page_content(session, title):
    r = session.get(API_URL, params={
        'action': 'query',
        'prop': 'revisions',
        'titles': title,
        'rvprop': 'content',
        'rvslots': 'main',
        'format': 'json'
    })
    pages = r.json().get('query', {}).get('pages', {})
    for page in pages.values():
        revs = page.get('revisions', [])
        if revs:
            return revs[0].get('slots', {}).get('main', {}).get('*', '')
    return ''

def is_redirect(session, title):
    r = session.get(API_URL, params={
        'action': 'query',
        'titles': title,
        'format': 'json',
        'redirects': 1
    })
    pages = r.json().get('query', {}).get('pages', {})
    for page_id, page_data in pages.items():
        if 'redirect' in page_data:
            return True
    return False

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
        'assert': 'user',
    })
    result = r.json()
    if result.get('edit', {}).get('result') == 'Success':
        new_revid = result['edit'].get('newrevid')
        old_revid = result['edit'].get('oldrevid')
        print(f"✅ Edited {title} — {summary}")
        return new_revid, old_revid
    else:
        print(f"❌ Failed to edit {title}: {result}")
        return None, None

def append_to_log(session, category_title, new_revid, old_revid):
    log_title = "User:Fixinbot/log"
    current_content = get_page_content(session, log_title) or ""

    diff_link = f"https://test.wikipedia.org/w/index.php?diff={new_revid}&oldid={old_revid}"
    new_entry = f"# [[:{category_title}]] — Removed <nowiki>{{{{popcat}}}}</nowiki> ([diff]({diff_link}))\n"

    updated_content = current_content.strip() + "\n" + new_entry
    save_page(session, log_title, updated_content, summary="Logging popcat removal")

def process_category(session, title):
    if is_redirect(session, title):
        print(f"⏩ Skipping redirect: {title}")
        return

    page_members = get_category_members(session, title, cmtype='page')
    if len(page_members) < 3:
        print(f"ℹ️ Still underpopulated: {title} ({len(page_members)} pages)")
        return

    content = get_page_content(session, title)
    if not content:
        print(f"❌ No content for {title}")
        return

    wikicode = mwparserfromhell.parse(content)
    popcat_templates = [t for t in wikicode.filter_templates() if t.name.strip().lower() == "popcat"]

    if popcat_templates:
        for t in popcat_templates:
            wikicode.remove(t)
        summary = "Bot: Removing {{popcat}} — now has 3 or more pages"
        new_revid, old_revid = save_page(session, title, str(wikicode), summary)
        if new_revid and old_revid:
            append_to_log(session, title, new_revid, old_revid)
        time.sleep(5)
    else:
        print(f"✔ No {{popcat}} in {title}")

def main():
    username = os.getenv("BOT_USERNAME")
    password = os.getenv("BOT_PASSWORD")
    if not username or not password:
        print("❌ Missing BOT_USERNAME or BOT_PASSWORD")
        sys.exit(1)

    session = login_and_get_session(username, password)

    underpopulated_cats = get_category_members(session, "Category:Underpopulated categories", cmtype='subcat')

    for cat in underpopulated_cats:
        process_category(session, cat['title'])

if __name__ == "__main__":
    main()
