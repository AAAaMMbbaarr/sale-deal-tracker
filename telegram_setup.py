"""
Step 4 setup: connect the tracker to your Telegram bot. Run this once.

Before running:
  1. Create a bot with @BotFather and copy its token.
  2. Send your bot any message (like "hi") from your phone.

Then run:
    python telegram_setup.py
"""

import json
import re

import requests

CONFIG_FILE = "telegram_config.json"


def find_chat_id(token):
    """Look at the messages your bot received and get your chat ID from them."""
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    data = requests.get(url, timeout=15).json()

    if not data.get("ok"):
        # Telegram says why, e.g. "Unauthorized" = wrong token.
        raise RuntimeError(f"Telegram said: {data.get('description')}")

    for update in reversed(data["result"]):  # newest message first
        message = update.get("message") or update.get("edited_message")
        if message:
            return message["chat"]["id"], message["chat"].get("first_name", "")
    return None, None


def send_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=15)
    return response.json().get("ok", False)


if __name__ == "__main__":
    token = input("Paste your bot token from BotFather and press Enter: ")
    token = "".join(token.split())  # remove any spaces or line breaks from pasting

    # A real token looks like 1234567890:AAH... with ~35 characters after the colon.
    if not re.fullmatch(r"\d+:[A-Za-z0-9_-]{30,}", token):
        print("\nThat doesn't look like a complete bot token.")
        print("It should look like 1234567890:AAH... (about 45 characters in total).")
        print("In Telegram, long-press BotFather's message, choose Copy, and try again.")
        raise SystemExit

    chat_id, name = find_chat_id(token)
    if chat_id is None:
        print("\nNo messages found for your bot yet.")
        print("Open your bot in Telegram, send it 'hi', then run this again.")
        raise SystemExit

    if send_message(token, chat_id, "✅ Sale Deal Tracker is connected! Deal alerts will show up here."):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"token": token, "chat_id": chat_id}, f, indent=2)
        print(f"\nConnected{', ' + name if name else ''}! Check Telegram for a test message.")
        print(f"Saved your settings in {CONFIG_FILE}. Keep that file private.")
    else:
        print("\nFound your chat, but couldn't send the test message. Try again.")
