"""
Add many products to products.txt at once.

Paste links one per line. The script opens each one, reads the product
name and current price, sets a target price for you, and adds it to
your watch list. No typing names or prices yourself.

How to run:
    python add_products.py
"""

import re
import time

from price_check import clean_amazon_url, get_details

PRODUCTS_FILE = "products.txt"
WAIT_BETWEEN_PRODUCTS = 5  # seconds, so the site doesn't block us


def product_id(url):
    """Short ID for a product, used to spot duplicates."""
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)  # Amazon
    if match:
        return match.group(1)
    match = re.search(r"[?&]pid=([A-Z0-9]+)", url)  # Flipkart
    if match:
        return match.group(1)
    return url.split("?")[0]


def short_name(title, words=5):
    """'MSI PRO H610M-E Motherboard, Micro-ATX - Supports ...' -> 'MSI PRO H610M-E Motherboard'"""
    title = re.split(r"[,(|]", title)[0]
    return " ".join(title.split()[:words])


def existing_ids():
    try:
        with open(PRODUCTS_FILE, encoding="utf-8") as f:
            return {
                product_id(line.split("|")[1].strip())
                for line in f
                if "|" in line and not line.strip().startswith("#")
            }
    except FileNotFoundError:
        return set()


def read_links():
    print("Paste your product links, one per line.")
    print("When you're done, press Enter on an empty line.\n")
    links = []
    while True:
        line = input().strip()
        if not line:
            break
        # Allow several links pasted on one line too.
        links += re.findall(r"https?://\S+", line)
    return links


if __name__ == "__main__":
    links = read_links()
    if not links:
        print("No links pasted.")
        raise SystemExit

    answer = input(
        "\nSet each target how many % below today's price? (Enter = 10): "
    ).strip()
    percent_below = float(answer) if answer else 10

    already = existing_ids()
    new_lines = []

    for i, url in enumerate(links, start=1):
        print(f"\n[{i}/{len(links)}] Reading {url[:60]}...")
        if product_id(url) in already:
            print("  Already in your list, skipping.")
            continue
        try:
            title, price = get_details(url)
        except Exception as error:
            print(f"  Couldn't read it: {error}")
            continue
        if not title or price is None:
            print("  Couldn't find the name or price, skipping.")
            continue

        target = round(price * (1 - percent_below / 100))
        name = short_name(title)
        print(f"  {name}: ₹{price:,.0f} now, target ₹{target:,.0f}")
        if "amazon." in url:
            url = clean_amazon_url(url)  # keep the list short and tidy
        new_lines.append(f"{name} | {url} | {target} |")
        already.add(product_id(url))

        if i < len(links):
            time.sleep(WAIT_BETWEEN_PRODUCTS)

    if new_lines:
        with open(PRODUCTS_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(new_lines) + "\n")
        print(f"\nAdded {len(new_lines)} product(s) to {PRODUCTS_FILE}.")
        print("Open it to change any target or add a bank offer.")
    else:
        print("\nNothing new was added.")
