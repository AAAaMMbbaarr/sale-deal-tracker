"""
Deal scanner: finds deals by itself on Amazon search pages.

Instead of watching products you picked, it reads a whole search
results page (e.g. "smartphones under ₹20,000") and alerts you about:
  - big discounts:  price is X% or more below the MRP
  - real drops:     price fell X% or more since the scanner last saw it

Setup: put your searches in searches.txt (see the notes inside it).

How to run:
    python deal_scanner.py            -> scan once
    python deal_scanner.py watch      -> scan every 15 minutes
    python deal_scanner.py watch 20   -> scan every 20 minutes
"""

import json
import os
import sys
import time

from bs4 import BeautifulSoup

from price_check import fetch_html, to_number
from tracker import send_telegram

SEARCHES_FILE = "searches.txt"
HISTORY_FILE = "scanner_history.json"  # prices seen before, to spot real drops
WAIT_BETWEEN_SEARCHES = 10  # seconds


def load_searches():
    searches = []
    with open(SEARCHES_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2:
                continue
            searches.append({
                "name": parts[0],
                "url": parts[1],
                "min_percent": float(parts[2]) if len(parts) > 2 and parts[2] else 40,
            })
    return searches


def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=1)


def read_amazon_results(html):
    """Pull every product (ID, name, price, MRP) out of an Amazon search page."""
    soup = BeautifulSoup(html, "html.parser")
    products = []

    for card in soup.select('div[data-component-type="s-search-result"]'):
        asin = card.get("data-asin")
        if not asin:
            continue

        heading = card.find("h2")
        if heading is None:
            continue
        title = heading.get("aria-label") or heading.get_text(" ", strip=True)

        # The selling price box is the one WITHOUT the "a-text-price" class;
        # the crossed-out MRP box has it.
        price_tag = card.select_one("span.a-price:not(.a-text-price) span.a-offscreen")
        mrp_tag = card.select_one("span.a-price.a-text-price span.a-offscreen")

        price = to_number(price_tag.get_text()) if price_tag else None
        mrp = to_number(mrp_tag.get_text()) if mrp_tag else None
        if price is None:
            continue  # sponsored boxes or out-of-stock items

        products.append({
            "asin": asin,
            "title": title,
            "price": price,
            "mrp": mrp,
            "url": f"https://www.amazon.in/dp/{asin}",
        })
    return products


def scan(search, history):
    print(f"\nScanning: {search['name']}")
    if "amazon." not in search["url"]:
        print("  Only Amazon search pages are supported for now, skipping.")
        return 0

    try:
        html = fetch_html(search["url"])
    except Exception as error:
        print(f"  Couldn't open the search page: {error}")
        return 0

    products = read_amazon_results(html)
    if not products:
        print("  Found no products. Amazon may have shown a bot check page.")
        return 0
    print(f"  Read {len(products)} products.")

    min_percent = search["min_percent"]
    deals = 0

    for p in products:
        seen = history.get(p["asin"], {})
        reasons = []

        # Signal 1: big discount off MRP.
        if p["mrp"] and p["mrp"] > p["price"]:
            off = (p["mrp"] - p["price"]) / p["mrp"] * 100
            if off >= min_percent:
                reasons.append(f"{off:.0f}% below MRP ₹{p['mrp']:,.0f}")

        # Signal 2: dropped since the last time we saw it (more trustworthy,
        # because sellers sometimes inflate the MRP).
        last = seen.get("last_price")
        if last and p["price"] < last:
            drop = (last - p["price"]) / last * 100
            if drop >= min_percent / 4:  # e.g. 10% drop when min_percent is 40
                reasons.append(f"dropped {drop:.0f}% from ₹{last:,.0f}")

        # Only alert if it's cheaper than the last price we alerted about.
        alerted_at = seen.get("alerted_price")
        if reasons and (alerted_at is None or p["price"] < alerted_at):
            deals += 1
            print(f"  🔥 ₹{p['price']:,.0f}  {p['title'][:60]}  ({'; '.join(reasons)})")
            send_telegram(
                f"🔥 DEAL FOUND ({search['name']})\n{p['title'][:100]}\n"
                f"Price: ₹{p['price']:,.0f}\n{chr(10).join(reasons)}\n\nBuy: {p['url']}"
            )
            seen["alerted_price"] = p["price"]

        seen["last_price"] = p["price"]
        seen["lowest_price"] = min(p["price"], seen.get("lowest_price", p["price"]))
        history[p["asin"]] = seen

    if deals == 0:
        print("  No new deals on this page.")
    return deals


def scan_all():
    history = load_history()
    searches = load_searches()
    total = 0
    for i, search in enumerate(searches):
        total += scan(search, history)
        if i < len(searches) - 1:
            time.sleep(WAIT_BETWEEN_SEARCHES)
    save_history(history)
    print("\n" + "-" * 40)
    print(f"{total} new deal(s) found.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "watch":
        minutes = int(sys.argv[2]) if len(sys.argv) > 2 else 15
        minutes = max(minutes, 10)  # search pages get blocked faster, so go slow
        print(f"Watch mode: scanning every {minutes} minutes. Press Ctrl+C to stop.")
        send_telegram(f"🔎 Deal scanner started. Scanning every {minutes} minutes.")
        try:
            while True:
                print(time.strftime("\n[%d %b %I:%M %p]"))
                scan_all()
                time.sleep(minutes * 60)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        scan_all()
