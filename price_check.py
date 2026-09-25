"""
Step 1 of the Sale Deal Tracker: read the product name and price
from an Amazon.in or Flipkart product page.

How to run:
  1. Install the two libraries (one time):
         pip install requests beautifulsoup4
  2. Run:
         python price_check.py
  3. When it asks, paste a product link copied from your browser
     and press Enter.
"""

import json
import re

import requests
from bs4 import BeautifulSoup

# ---- Put your product link here ----
PRODUCT_URL = "https://www.amazon.in/dp/XXXXXXXXXX"


# Websites block requests that don't look like they come from a browser.
# These headers make our request look like a normal Chrome visit.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
}


def clean_amazon_url(url):
    """
    Amazon links carry a lot of tracking junk after the product ID.
    Every product has a 10-character ID (the ASIN) after /dp/.
    We rebuild a short, clean link from it: https://www.amazon.in/dp/B0CC9G49JQ
    """
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
    if match:
        return f"https://www.amazon.in/dp/{match.group(1)}"
    return url


def fetch_html(url):
    """Download the page and return its HTML as text."""
    # A Session keeps cookies between requests, like a real browser does.
    session = requests.Session()
    session.headers.update(HEADERS)

    if "amazon." in url:
        url = clean_amazon_url(url)
        # Visit the homepage first to pick up cookies, then open the product.
        session.get("https://www.amazon.in/", timeout=15)

    response = session.get(url, timeout=15)

    if response.status_code != 200:
        # Save what the site sent back so we can see why it refused.
        with open("debug_page.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        raise RuntimeError(
            f"The site returned error {response.status_code} for {url}\n"
            "404/503 here usually means the site suspected a bot.\n"
            "Saved its reply as debug_page.html so we can check it."
        )
    return response.text


def to_number(text):
    """Turn a price like '₹1,23,999.00' into the number 123999.0"""
    if text is None:
        return None
    digits = re.sub(r"[^\d.]", "", str(text))
    return float(digits) if digits else None


def get_amazon_details(soup):
    """Amazon keeps the title in #productTitle and the price in a-price spans."""
    title_tag = soup.select_one("#productTitle")

    # Try the main price box first, then fall back to any price on the page.
    # Amazon uses different price boxes on different pages, so we try several.
    price_tag = (
        soup.select_one("#corePriceDisplay_desktop_feature_div span.priceToPay span.a-offscreen")
        or soup.select_one("#corePriceDisplay_desktop_feature_div span.a-offscreen")
        or soup.select_one("#corePrice_feature_div span.a-offscreen")
        or soup.select_one("#apex_desktop span.a-offscreen")
        or soup.select_one("#priceblock_dealprice")
        or soup.select_one("#priceblock_ourprice")
        or soup.select_one("span.priceToPay span.a-offscreen")
        or soup.select_one("span.a-price span.a-offscreen")
        or soup.select_one("span.a-price-whole")
    )

    title = title_tag.get_text(strip=True) if title_tag else None
    price = to_number(price_tag.get_text()) if price_tag else None

    if price is None:
        price = find_hidden_amazon_price(soup)
    return title, price


def find_hidden_amazon_price(soup):
    """
    Backup plan: Amazon also hides the price inside the page's code
    (hidden form fields and bits of JSON), even when the visible price
    box is missing. We check those spots one by one.
    """
    # 1. Hidden form fields that Amazon uses for the cart.
    for field_id in ("twister-plus-price-data-price", "attach-base-product-price"):
        field = soup.find("input", id=field_id)
        if field and field.get("value"):
            price = to_number(field["value"])
            if price:
                return price

    # 2. Price stored in the page's JSON data, e.g. "priceAmount":5509.00
    raw = str(soup)
    patterns = [
        r'"priceAmount"\s*:\s*([\d.]+)',
        r'"displayPrice"\s*:\s*"[^\d"]*([\d,]+(?:\.\d+)?)"',
        r'"buyingPrice"\s*:\s*([\d.]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, raw)
        if match:
            price = to_number(match.group(1))
            if price:
                return price

    # 3. Any "a-price-whole" number anywhere on the page.
    whole = soup.find(class_="a-price-whole")
    if whole:
        return to_number(whole.get_text())

    return None


def get_flipkart_details(soup):
    """
    Flipkart's CSS class names change often, so we first look for the
    structured product data (JSON-LD) that many product pages include.
    """
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "Product":
                offers = item.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                return item.get("name"), to_number(offers.get("price"))

    # Fallback: page title + first rupee amount on the page (less reliable).
    title_tag = soup.find("h1") or soup.find("meta", property="og:title")
    if title_tag is None:
        title = None
    elif title_tag.name == "meta":
        title = title_tag.get("content")
    else:
        title = title_tag.get_text(strip=True)

    match = re.search(r"₹\s?[\d,]+", soup.get_text())
    price = to_number(match.group()) if match else None
    return title, price


def get_details(url):
    html = fetch_html(url)

    # Keep a copy of the page we got, to help with debugging.
    with open("debug_page.html", "w", encoding="utf-8") as f:
        f.write(html)

    # Amazon shows a "Robot Check" page when it thinks we're a bot.
    if "validateCaptcha" in html or "Robot Check" in html:
        raise RuntimeError(
            "Amazon showed a CAPTCHA page. Wait a few minutes and try again."
        )

    soup = BeautifulSoup(html, "html.parser")

    if "amazon." in url:
        return get_amazon_details(soup)
    if "flipkart.com" in url:
        return get_flipkart_details(soup)
    raise ValueError("Only Amazon.in and Flipkart links are supported.")


if __name__ == "__main__":
    # Ask for the link when the script runs, so you don't have to edit the file.
    url = input("Paste the Amazon/Flipkart product link and press Enter: ").strip()
    if not url:
        url = PRODUCT_URL

    title, price = get_details(url)

    if price is None:
        print("Couldn't find the price.")
        print(f"Title found: {title}")
        if title is None:
            print("-> No product title either, so Amazon probably sent a")
            print("   'bot check' page instead of the real product page.")
        else:
            print("-> The product page loaded. It may be out of stock,")
            print("   or the price sits in a spot the script doesn't know yet.")
        print("Saved the page as debug_page.html - open it in Chrome to see it.")
    else:
        print(f"Product: {title}")
        print(f"Price:   ₹{price:,.0f}")
