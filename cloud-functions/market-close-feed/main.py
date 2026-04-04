import datetime
import re
import time
import xml.etree.ElementTree as ET
import zoneinfo
from email.utils import formatdate
from time import mktime
from typing import Optional

import functions_framework
import requests
from bs4 import BeautifulSoup
from google.cloud import storage

ET_TZ = zoneinfo.ZoneInfo("America/New_York")

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

EJ_URL = "https://www.edwardjones.com/us-en/market-news-insights/stock-market-news/daily-market-recap"
EJ_RETRY_DELAY = 120
EJ_MAX_RETRIES = 2


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


def _scrape_ej(today: datetime.date) -> Optional[str]:
    resp = requests.get(EJ_URL, headers=YAHOO_HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    container = soup.select_one("div.rich-text.relative")
    if not container:
        return None

    date_el = container.find("p")
    if not date_el or not date_el.find("strong"):
        return None

    date_text = date_el.find("strong").get_text()
    date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", date_text)
    if not date_match:
        return None

    parts = date_match.group(1).split("/")
    ej_date = datetime.date(int(parts[2]), int(parts[0]), int(parts[1]))
    if ej_date != today:
        return None

    summary_list = container.find("ul")
    if not summary_list:
        return None

    items = []
    for li in summary_list.find_all("li"):
        items.append(str(li))
    return "".join(items) if items else None


def fetch_ej_summary(today: datetime.date) -> Optional[str]:
    for attempt in range(1 + EJ_MAX_RETRIES):
        result = _scrape_ej(today)
        if result is not None:
            return result
        if attempt < EJ_MAX_RETRIES:
            time.sleep(EJ_RETRY_DELAY)
    return None


def format_index_html(name: str, data: dict) -> str:
    arrow = "\u25b2" if data["change"] >= 0 else "\u25bc"
    sign = "+" if data["change"] >= 0 else ""
    color = "#22c55e" if data["change"] >= 0 else "#ef4444"
    return (
        f'<div class="idx-row">'
        f'<strong class="idx-name">{name}</strong>'
        f'<span class="idx-price">{data["price"]:,.2f}</span>'
        f'<span class="idx-chg" style="color:{color}">{arrow} {sign}{data["change"]:,.2f} ({sign}{data["pct"]:.2f}%)</span>'
        f'</div>'
    )


def format_mover_line(m: dict, is_gainer: bool) -> str:
    sign = "+" if is_gainer else ""
    name = m["name"][:18]
    return f"{m['symbol']:<5} {name:<18} ${m['price']:>8,.2f} {sign}{m['pct']:.1f}%"


def build_description(date_str: str, indices: dict, gainers: list, losers: list, ej_summary: Optional[str]) -> str:
    parts = [f"<h2 style=\"margin:0 0 12px\">Market Close \u2014 {date_str}</h2>"]

    for name in INDEX_URLS:
        parts.append(format_index_html(name, indices[name]))

    parts.append('<div class="movers">')

    parts.append('<div class="mover-col"><h3 style="margin:0 0 4px">\u25b2 Gainers</h3><pre style="margin:0;font-size:13px">')
    for g in gainers:
        parts.append(format_mover_line(g, True))
    parts.append("</pre></div>")

    parts.append('<div class="mover-col"><h3 style="margin:0 0 4px">\u25bc Losers</h3><pre style="margin:0;font-size:13px">')
    for l in losers:
        parts.append(format_mover_line(l, False))
    parts.append("</pre></div>")

    parts.append("</div>")

    if ej_summary:
        parts.append(f'<div style="margin-top:16px;line-height:1.5">{ej_summary}</div>')

    return "\n".join(parts)


def build_rss(date_str: str, market_date: datetime.date, description: str) -> str:
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
    ET.SubElement(item, "link").text = f"https://storage.googleapis.com/{BUCKET}/market-close.html"
    ET.SubElement(item, "pubDate").text = rfc_date
    guid = ET.SubElement(item, "guid", isPermaLink="false")
    guid.text = f"market-close-{market_date.isoformat()}"

    desc_el = ET.SubElement(item, "description")
    desc_el.text = description

    xml_bytes = ET.tostring(rss, encoding="unicode", xml_declaration=False)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_bytes}'


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 720px;
           margin: 40px auto; padding: 0 20px; color: #1a1a1a; background: #fafafa; }}
    .card {{ background: #fff; border-radius: 12px; padding: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
    .meta {{ color: #666; font-size: 14px; margin-bottom: 16px; }}
    .idx-row {{ display: flex; padding: 4px 0; white-space: nowrap; }}
    .idx-name {{ width: 90px; flex-shrink: 0; }}
    .idx-price {{ width: 90px; text-align: right; flex-shrink: 0; }}
    .idx-chg {{ margin-left: 12px; flex-shrink: 0; }}
    .movers {{ display: flex; gap: 24px; margin-top: 16px; }}
    .mover-col {{ flex: 1; min-width: 0; }}
    pre {{ overflow-x: auto; }}
    @media (max-width: 600px) {{
      .movers {{ flex-direction: column; gap: 16px; }}
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="meta">{date}</div>
    {content}
  </div>
</body>
</html>
"""


def upload_to_gcs(xml_content: str) -> str:
    client = storage.Client(project=PROJECT)
    bucket = client.bucket(BUCKET)

    blob = bucket.blob(BLOB_NAME)
    blob.upload_from_string(xml_content, content_type="application/rss+xml")
    return f"https://storage.googleapis.com/{BUCKET}/{BLOB_NAME}"


def upload_html(date_str: str, title: str, description: str) -> None:
    client = storage.Client(project=PROJECT)
    bucket = client.bucket(BUCKET)
    html = HTML_TEMPLATE.format(title=title, date=date_str, content=description)
    blob = bucket.blob("market-close.html")
    blob.upload_from_string(html, content_type="text/html")


def _parse_date_param(request) -> datetime.date | None:
    date_param = request.args.get("date")
    if not date_param:
        return None
    return datetime.date.fromisoformat(date_param)


@functions_framework.http
def market_close_feed(request):
    today = _parse_date_param(request) or datetime.datetime.now(ET_TZ).date()
    date_str = today.strftime("%B %d, %Y")

    indices = {}
    for name, url in INDEX_URLS.items():
        indices[name] = fetch_index(url)

    gainers = fetch_movers(GAINERS_URL, 10)
    losers = fetch_movers(LOSERS_URL, 10)

    title = f"Market Close \u2014 {date_str}"
    description = build_description(date_str, indices, gainers, losers, None)
    xml = build_rss(date_str, today, description)
    public_url = upload_to_gcs(xml)
    upload_html(date_str, title, description)

    ej_summary = fetch_ej_summary(today)
    if ej_summary:
        description = build_description(date_str, indices, gainers, losers, ej_summary)
        xml = build_rss(date_str, today, description)
        upload_to_gcs(xml)
        upload_html(date_str, title, description)

    return f"Published to {public_url}", 200
