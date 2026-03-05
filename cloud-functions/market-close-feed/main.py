import datetime
import xml.etree.ElementTree as ET
from email.utils import formatdate
from time import mktime
from typing import Optional

import feedparser
import functions_framework
import requests
from google.cloud import storage

PROJECT = "glossy-reserve-153120"
BUCKET = "myfeeds-market-close"
BLOB_NAME = "market-close.xml"

YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0"}

INDEX_URLS = {
    "S&P 500": "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC",
    "Dow Jones": "https://query1.finance.yahoo.com/v8/finance/chart/%5EDJI",
    "NASDAQ": "https://query1.finance.yahoo.com/v8/finance/chart/%5EIXIC",
}

GAINERS_URL = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=day_gainers"
LOSERS_URL = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=day_losers"

EJ_FEED_URL = "https://fetchrss.com/feed/1vxzOo2J91bu1vxz7I7xYGEE.rss"


def fetch_index(url: str) -> dict:
    resp = requests.get(url, headers=YAHOO_HEADERS, timeout=15)
    resp.raise_for_status()
    meta = resp.json()["chart"]["result"][0]["meta"]
    price = meta["regularMarketPrice"]
    prev = meta["previousClose"]
    change = price - prev
    pct = (change / prev) * 100
    return {"price": price, "change": change, "pct": pct}


def fetch_movers(url: str, count: int = 10) -> list[dict]:
    resp = requests.get(url, headers=YAHOO_HEADERS, timeout=15)
    resp.raise_for_status()
    quotes = resp.json()["finance"]["result"][0]["quotes"][:count]
    results = []
    for q in quotes:
        results.append({
            "symbol": q.get("symbol", "???"),
            "name": q.get("shortName", q.get("longName", "")),
            "price": q.get("regularMarketPrice", 0),
            "pct": q.get("regularMarketChangePercent", 0),
        })
    return results


def fetch_ej_summary() -> Optional[str]:
    try:
        feed = feedparser.parse(EJ_FEED_URL)
        if feed.entries:
            desc = feed.entries[0].get("description", "") or feed.entries[0].get("summary", "")
            return desc.strip() if desc else None
    except Exception:
        pass
    return None


def format_index_line(name: str, data: dict) -> str:
    arrow = "\u25b2" if data["change"] >= 0 else "\u25bc"
    sign = "+" if data["change"] >= 0 else ""
    return (
        f"{name + ':':<11} {data['price']:>10,.2f}  "
        f"{arrow} {sign}{data['change']:>7,.2f}  "
        f"({sign}{data['pct']:.2f}%)"
    )


def format_mover_line(m: dict, is_gainer: bool) -> str:
    sign = "+" if is_gainer else ""
    name = m["name"][:18]
    return f"{m['symbol']:<5} {name:<18} ${m['price']:>8,.2f} {sign}{m['pct']:.1f}%"


def wrap_text(text: str, width: int = 72) -> str:
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        if current_line and len(current_line) + 1 + len(word) > width:
            lines.append(current_line)
            current_line = word
        else:
            current_line = f"{current_line} {word}" if current_line else word
    if current_line:
        lines.append(current_line)
    return "\n".join(lines)


def build_description(date_str: str, indices: dict, gainers: list, losers: list, ej_summary: Optional[str]) -> str:
    lines = [f"Market Close \u2014 {date_str}", ""]

    for name in INDEX_URLS:
        lines.append(format_index_line(name, indices[name]))
    lines.append("")

    header_g = "\u2500\u2500 GAINERS "
    header_l = "\u2500\u2500 LOSERS "
    lines.append(f"{header_g:\u2500<38} {header_l:\u2500<38}")

    max_rows = max(len(gainers), len(losers))
    for i in range(max_rows):
        g_line = format_mover_line(gainers[i], True) if i < len(gainers) else ""
        l_line = format_mover_line(losers[i], False) if i < len(losers) else ""
        lines.append(f"{g_line:<38} \u2502  {l_line}")
    lines.append("")

    if ej_summary:
        lines.append(wrap_text(ej_summary))

    return "\n".join(lines)


def build_rss(date_str: str, description: str) -> str:
    rfc_date = formatdate(
        mktime(datetime.datetime.now(datetime.timezone.utc).timetuple()),
        usegmt=True,
    )

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Market Close"
    ET.SubElement(channel, "link").text = f"https://storage.googleapis.com/{BUCKET}/{BLOB_NAME}"
    ET.SubElement(channel, "description").text = "Daily US market close summary"
    ET.SubElement(channel, "lastBuildDate").text = rfc_date

    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = f"Market Close \u2014 {date_str}"
    ET.SubElement(item, "pubDate").text = rfc_date
    guid = ET.SubElement(item, "guid", isPermaLink="false")
    guid.text = f"market-close-{datetime.date.today().isoformat()}"

    desc_el = ET.SubElement(item, "description")
    desc_el.text = f"<pre>{description}</pre>"

    xml_bytes = ET.tostring(rss, encoding="unicode", xml_declaration=False)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_bytes}'


def upload_to_gcs(xml_content: str) -> str:
    client = storage.Client(project=PROJECT)
    bucket = client.bucket(BUCKET)
    blob = bucket.blob(BLOB_NAME)
    blob.upload_from_string(xml_content, content_type="application/rss+xml")
    return f"https://storage.googleapis.com/{BUCKET}/{BLOB_NAME}"


@functions_framework.http
def market_close_feed(request):
    today = datetime.date.today()
    date_str = today.strftime("%B %d, %Y")

    indices = {}
    for name, url in INDEX_URLS.items():
        indices[name] = fetch_index(url)

    gainers = fetch_movers(GAINERS_URL, 10)
    losers = fetch_movers(LOSERS_URL, 10)
    ej_summary = fetch_ej_summary()

    description = build_description(date_str, indices, gainers, losers, ej_summary)
    xml = build_rss(date_str, description)
    public_url = upload_to_gcs(xml)

    return f"Published to {public_url}", 200
