"""
Steps 2 + 3 of the Sale Deal Tracker.

Reads your watch list from products.txt, checks each price,
works out the price after the bank offer, and tells you
which ones are below your target.

How to run (keep price_check.py and products.txt in the same folder):
    python tracker.py
"""

import json
import os
import re
import time

import requests

from price_check import get_details  # the Step 1 script does the price reading

PRODUCTS_FILE = "products.txt"
TELEGRAM_CONFIG = "telegram_config.json"  # made by telegram_setup.py
WAIT_BETWEEN_PRODUCTS = 5  # seconds; checking too fast can get you blocked


def send_telegram(text):
    """Send a message to your phone. Quietly skips if Telegram isn't set up."""
    if not os.path.exists(TELEGRAM_CONFIG):
        return
    with open(TELEGRAM_CONFIG, encoding="utf-8") as f:
        config = json.load(f)
    try:
        requests.post(
            f"https://api.telegram.org/bot{config['token']}/sendMessage",
            data={"chat_id": config["chat_id"], "text": text},
            timeout=15,
        )
    except requests.RequestException as error:
        print(f"  (Couldn't send the Telegram alert: {error})")


def load_products(filename):
    """Read products.txt and turn each line into a small dictionary."""
    products = []
    with open(filename, encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue  # skip empty lines and notes

            parts = [part.strip() for part in line.split("|")]
            if len(parts) < 3:
                print(f"Skipping line {line_number}: needs at least name | link | target")
                continue

            products.append({
                "name": parts[0],
                "url": parts[1],
                "target": float(re.sub(r"[^\d.]", "", parts[2])),
                "offer": parts[3] if len(parts) > 3 else "",
            })
    return products


def apply_bank_offer(price, offer):
    """
    Work out the price after the bank offer.
    Returns (effective_price, short description of the offer).
    """
    if not offer:
        return price, ""

    text = offer.lower()

    # Flat discount, e.g. "flat 1500 SBI"
    flat = re.search(r"flat\s*₹?\s*([\d,]+)", text)
    if flat:
        discount = float(flat.group(1).replace(",", ""))
        return max(price - discount, 0), offer

    # Percentage discount, e.g. "10% HDFC max 1000"
    percent = re.search(r"([\d.]+)\s*%", text)
    if percent:
        discount = price * float(percent.group(1)) / 100
        cap = re.search(r"max\s*₹?\s*([\d,]+)", text)
        if cap:
            discount = min(discount, float(cap.group(1).replace(",", "")))
        return price - discount, offer

    print(f"  (Couldn't understand the offer '{offer}', ignoring it)")
    return price, ""


def check_product(product, alerted=None):
    """
    Check one product and print the result. Returns True if it's a deal.

    `alerted` remembers the price we last alerted about for each product,
    so watch mode doesn't message you every 10 minutes about the same deal.
    You only get a new alert if the price drops even further.
    """
    print(f"\nChecking: {product['name']}")
    try:
        _, price = get_details(product["url"])
    except Exception as error:
        # One broken link shouldn't stop the others from being checked.
        print(f"  Couldn't check it: {error}")
        return False

    if price is None:
        print("  Couldn't find the price on the page.")
        return False

    effective, offer = apply_bank_offer(price, product["offer"])
    target = product["target"]

    print(f"  Price:        ₹{price:,.0f}")
    if offer:
        print(f"  With offer:   ₹{effective:,.0f}   ({offer})")
    print(f"  Your target:  ₹{target:,.0f}")

    if effective <= target:
        print("  ✅ DEAL! It's at or below your target.")

        last = alerted.get(product["url"]) if alerted is not None else None
        if last is not None and effective >= last:
            print("  (Already sent you this deal, not messaging again.)")
            return True

        alert = f"🔥 DEAL: {product['name']}\nPrice: ₹{price:,.0f}\n"
        if offer:
            alert += f"With offer: ₹{effective:,.0f} ({offer})\n"
        alert += f"Your target: ₹{target:,.0f}\n\nBuy: {product['url']}"
        send_telegram(alert)
        if alerted is not None:
            alerted[product["url"]] = effective
        return True

    # Price went back above target: forget the old alert, so a new drop alerts again.
    if alerted is not None:
        alerted.pop(product["url"], None)
    print(f"  ❌ Not yet. ₹{effective - target:,.0f} above your target.")
    return False


def check_all(alerted=None):
    """One round: check every product in products.txt."""
    products = load_products(PRODUCTS_FILE)  # re-read, so your edits apply
    print(f"Checking {len(products)} product(s)...")

    deals = []
    for i, product in enumerate(products):
        if check_product(product, alerted):
            deals.append(product["name"])
        if i < len(products) - 1:
            time.sleep(WAIT_BETWEEN_PRODUCTS)

    print("\n" + "-" * 40)
    if deals:
        print(f"{len(deals)} deal(s) found: " + ", ".join(deals))
    else:
        print("No deals below your targets right now.")


if __name__ == "__main__":
    import sys

    # Normal run:   python tracker.py          -> checks once
    # Watch mode:   python tracker.py watch    -> checks every 10 minutes
    # Custom gap:   python tracker.py watch 15 -> checks every 15 minutes
    if len(sys.argv) > 1 and sys.argv[1] == "watch":
        minutes = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        minutes = max(minutes, 5)  # never faster than 5 min, or you'll get blocked
        alerted = {}
        print(f"Watch mode: checking every {minutes} minutes. Press Ctrl+C to stop.\n")
        send_telegram(f"👀 Tracker started. Checking every {minutes} minutes.")
        try:
            while True:
                print(time.strftime("[%d %b %I:%M %p]"))
                check_all(alerted)
                print(f"\nNext check in {minutes} minutes...\n")
                time.sleep(minutes * 60)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        check_all()
