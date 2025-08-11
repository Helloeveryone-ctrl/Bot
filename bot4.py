import os
import requests
import sys
import re
import datetime

API_URL = "https://en.wikipedia.org/w/api.php"

HEADERS = {
    'User-Agent': 'Fixinbot/1.1 (https://en.wikipedia.org/wiki/User:Fixinbot)'
}

DECLINE_IP = '103.239.4.205'  # IP used in bot signature in declined message

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

def is_empty_request(request_text):
    # Check empty categorytree: no text between categorytree tags except comments or whitespace
    catree_match = re.search(r'<categorytree[^>]*>(.*?)</categorytree>', request_text, re.DOTALL)
    if catree_match:
        catree_content = catree_match.group(1).strip()
        # Remove HTML comments and whitespace, if nothing remains -> empty
        catree_content_clean = re.sub(r'<!--.*?-->', '', catree_content, flags=re.DOTALL).strip()
        if catree_content_clean != '':
            return False
    else:
        # No categorytree at all means empty
        return True

    # Check example pages lines like "* [[something]]"
    example_pages = re.findall(r'^\* \[\[(.*?)\]\]', request_text, re.MULTILINE)
    if not example_pages:
        return True
    # If all example pages empty or whitespace only, treat as empty
    if all(ep.strip() == '' for ep in example_pages):
        return True

    # Could add parent category checks if desired (optional)

    return False

def extract_category_name(header_text):
    match = re.search(r'== Category request: \[\[:Category:(.*?)\]\] ==', header_text)
    if match:
        return match.group(1).strip()
    return 'Put category name here'

def declined_text(category_name, ip):
    timestamp = datetime.datetime.utcnow().strftime('%H:%M, %-d %B %Y (UTC)')
    return f"""== Category request: [[:Category:{category_name}]] ==

{{{{AfC-c|d}}}}
<categorytree mode=pages showcount=on depth=0>
<!-- Type the EXACT NAME of the requested category below this line -->

<!-- Type the EXACT NAME of the requested category above this line -->
</categorytree>

Example pages which belong to this category:
<!-- List THREE examples of pages that would fall into this category -->
* [[ ]]
* [[ ]]
* [[ ]]

Parent category/categories:
<!-- Would this category be a subcategory of any other categories? If yes, list them here -->
* [[:Category:Put parent category name here]]
* [[:Category:Put 2nd parent category name here (etc) - delete these lines if none]]

[[Special:Contributions/{ip}|{ip}]] ([[User talk:{ip}|talk]]) {timestamp}
* [[Image:Symbol declined.svg|20px]] '''Declined'''. We cannot accept empty submissions. (Bot) ~~~~
"""

def run_bot():
    username = os.getenv("BOT_USERNAME")
    password = os.getenv("BOT_PASSWORD")
    page_title = "Wikipedia:Articles for creation/Categories"

    if not username or not password:
        print("❌ Missing BOT_USERNAME or BOT_PASSWORD environment variables")
        sys.exit(1)

    session = login_and_get_session(username, password)
    text = get_current_page_text(session, page_title)
    if not text.strip():
        print(f"ℹ️ Page {page_title} is empty or not found.")
        return

    # Split by category request header lines, keep the delimiter in result
    parts = re.split(r'(== Category request: \[\[:Category:.*?\]\] ==)', text)

    # The parts will look like: [prefix text, header1, content1, header2, content2, ...]
    # We'll process pairs of (header, content)
    new_text_parts = []
    if parts[0].strip():
        new_text_parts.append(parts[0])  # Any leading text before first request

    changed = False
    for i in range(1, len(parts), 2):
        header = parts[i]
        content = ''
        if i+1 < len(parts):
            content = parts[i+1]

        full_request_text = header + content

        if is_empty_request(full_request_text):
            cat_name = extract_category_name(header)
            replacement = declined_text(cat_name, DECLINE_IP)
            new_text_parts.append(replacement)
            changed = True
            print(f"Declining empty request for category: {cat_name}")
        else:
            new_text_parts.append(full_request_text)

    new_page_text = '\n'.join(new_text_parts)

    if changed:
        token = get_csrf_token(session)
        r = session.post(API_URL, data={
            'action': 'edit',
            'title': page_title,
            'text': new_page_text,
            'token': token,
            'format': 'json',
            'bot': True,
            'summary': 'Bot: Declining empty category request(s)',
            'assert': 'user',
        })
        result = r.json()
        if 'error' in result:
            print(f"❌ Edit failed: {result['error']}")
            sys.exit(1)
        elif result.get('edit', {}).get('result') == 'Success':
            print(f"✅ Edited page {page_title} with declined empty requests")
        else:
            print(f"❌ Unexpected edit response: {result}")
    else:
        print("✅ No empty requests to decline found.")

if __name__ == "__main__":
    run_bot()
