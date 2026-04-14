import os
import requests
import sys
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

API_URL = "https://en.wikipedia.org/w/api.php"

HEADERS = {
    "User-Agent": "Fixinbot/4.1 (https://en.wikipedia.org/wiki/User:Fixinbot)"
}


def safe_json(response, context=""):
    """Safely parse JSON responses."""
    try:
        return response.json()
    except Exception:
        print(f"⚠️ Non-JSON response during {context}")
        print(response.text[:200])
        return {}


def format_timestamp(ts):
    if ts in ("—", None):
        return "—"
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        return dt.strftime("%B %d, %Y, %H:%M:%S UTC")
    except Exception:
        return ts


def login_and_get_session(username, password):
    session = requests.Session()
    session.headers.update(HEADERS)

    r1 = session.get(API_URL, params={
        "action": "query",
        "meta": "tokens",
        "type": "login",
        "format": "json"
    }, timeout=20)

    data = safe_json(r1, "login token")
    login_token = data.get("query", {}).get("tokens", {}).get("logintoken")

    r2 = session.post(API_URL, data={
        "action": "login",
        "lgname": username,
        "lgpassword": password,
        "lgtoken": login_token,
        "format": "json"
    }, timeout=20)

    result = safe_json(r2, "login")
    if result.get("login", {}).get("result") != "Success":
        print(f"❌ Login failed: {result}")
        sys.exit(1)

    print(f"✅ Logged in as {username}")
    return session


def get_admins(session):
    admins = []
    aufrom = None

    while True:
        params = {
            "action": "query",
            "list": "allusers",
            "augroup": "sysop",
            "aulimit": "max",
            "format": "json"
        }

        if aufrom:
            params["aufrom"] = aufrom

        r = session.get(API_URL, params=params, timeout=20)
        data = safe_json(r, "get_admins")

        users = data.get("query", {}).get("allusers", [])
        admins.extend([u["name"] for u in users])

        if "continue" in data:
            aufrom = data["continue"]["aufrom"]
        else:
            break

    return admins


def fetch_user_activity(session, username):
    last_edit = "—"
    last_log = "—"

    try:
        r1 = session.get(API_URL, params={
            "action": "query",
            "list": "usercontribs",
            "ucuser": username,
            "uclimit": 1,
            "ucprop": "timestamp|title",
            "ucdir": "older",
            "format": "json"
        }, timeout=20)

        data1 = safe_json(r1, f"usercontribs {username}")
        contribs = data1.get("query", {}).get("usercontribs", [])

        if contribs:
            last_edit = contribs[0]["timestamp"]

        r2 = session.get(API_URL, params={
            "action": "query",
            "list": "logevents",
            "leuser": username,
            "lelimit": 1,
            "ledir": "older",
            "format": "json"
        }, timeout=20)

        data2 = safe_json(r2, f"logevents {username}")
        logs = data2.get("query", {}).get("logevents", [])

        if logs:
            last_log = logs[0]["timestamp"]

    except Exception as e:
        print(f"⚠️ Error fetching activity for {username}: {e}")

    if last_edit != "—" and last_log != "—":
        last_activity = max(last_edit, last_log)
    elif last_edit != "—":
        last_activity = last_edit
    elif last_log != "—":
        last_activity = last_log
    else:
        last_activity = None

    return {
        "username": username,
        "last_edit": last_edit,
        "last_log": last_log,
        "last_activity": last_activity
    }


def get_all_activities(session, admins):
    results = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_user_activity, session, u): u for u in admins}

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

    results.sort(key=lambda x: x["last_activity"] or "0000", reverse=True)
    return results


def get_csrf_token(session):
    r = session.get(API_URL, params={
        "action": "query",
        "meta": "tokens",
        "format": "json"
    }, timeout=20)

    data = safe_json(r, "csrf token")
    return data.get("query", {}).get("tokens", {}).get("csrftoken")


def get_current_page_text(session, title):
    r = session.get(API_URL, params={
        "action": "query",
        "prop": "revisions",
        "titles": title,
        "rvslots": "main",
        "rvprop": "content",
        "format": "json"
    }, timeout=20)

    data = safe_json(r, "get page text")
    pages = data.get("query", {}).get("pages", {})

    for page_id in pages:
        return pages[page_id].get("revisions", [{}])[0].get("slots", {}).get("main", {}).get("*", "")

    return ""


def save_to_page(session, page_title, admins_data):
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
        table_lines.append(f'| {format_timestamp(admin["last_edit"])}')
        table_lines.append(f'| {format_timestamp(admin["last_log"])}')

    table_lines.append('|}')
    new_table = "\n".join(table_lines)

    current_text = get_current_page_text(session, page_title)

    if re.search(r'\{\| class="wikitable sortable".*?\|\}', current_text, re.S):
        new_text = re.sub(r'\{\| class="wikitable sortable".*?\|\}', new_table, current_text, flags=re.S)
    else:
        new_text = current_text + "\n\n== Active admins ==\n" + new_table

    token = get_csrf_token(session)

    r = session.post(API_URL, data={
        "action": "edit",
        "title": page_title,
        "text": new_text,
        "token": token,
        "format": "json",
        "bot": True,
        "summary": "Updating active admins table (bot)",
        "assert": "user"
    }, timeout=20)

    result = safe_json(r, "edit page")

    if "error" in result:
        print(f"❌ Edit error: {result}")
        sys.exit(1)
    elif result.get("edit", {}).get("result") == "Success":
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

    admins_data = get_all_activities(session, admins)

    save_to_page(session, save_page, admins_data)


if __name__ == "__main__":
    run_bot()
