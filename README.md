# Fixinbot

This bot script cleans up the Wikimedia page `User:Fixinbot/Updates` by:

- Removing entries for pages that have been deleted
- Removing duplicate page links
- Removing update sections older than 7 days

---

## Features

- Logs into Wikimedia API with provided bot credentials
- Reads the current content of the updates page
- Detects and removes outdated sections (older than 7 days)
- Checks which pages still exist and removes links to deleted pages
- Removes duplicate page links
- Saves the cleaned content back to the updates page
- Handles API errors including IP blocks and login failures

---

## Requirements

- Python 3.6+
- `requests` library

Install dependencies:

```bash
pip install requests
