import xml.etree.ElementTree as ET
import requests
from datetime import datetime, timezone
import time


RSS_FEEDS = {
    "日本経済新聞": "https://www.nikkei.com/news/latest/feed/?bn=20",
    "Reuters 日本": "https://feeds.reuters.com/reuters/JPdomesticNews",
    "Bloomberg Japan": "https://feeds.bloomberg.com/jp/news/topstories.rss",
    "Yahoo Finance JP": "https://finance.yahoo.co.jp/news/rss",
    "Reuters Markets": "https://feeds.reuters.com/reuters/businessNews",
}

MACRO_KEYWORDS = [
    "金利", "利上げ", "利下げ", "日銀", "BOJ", "FRB", "Fed", "Federal Reserve",
    "インフレ", "CPI", "GDP", "雇用", "失業率", "為替", "円安", "円高",
    "景気後退", "リセッション", "TOPIX", "日経平均", "ダウ", "S&P",
    "半導体", "AI", "geopolitical", "地政学", "制裁", "関税", "tariff",
    "原油", "エネルギー", "中国", "アメリカ", "ウクライナ",
]


def _parse_rss(url: str, timeout: int = 8) -> list[dict]:
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception:
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []

    # RSS 2.0
    for item in root.findall(".//item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub = item.findtext("pubDate", "").strip()
        desc = item.findtext("description", "").strip()
        if title:
            items.append({"title": title, "link": link, "published": pub, "summary": desc[:200]})

    # Atom
    if not items:
        for entry in root.findall("atom:entry", ns):
            title = entry.findtext("atom:title", "", ns).strip()
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            pub = entry.findtext("atom:updated", "", ns).strip()
            summary = entry.findtext("atom:summary", "", ns).strip()
            if title:
                items.append({"title": title, "link": link, "published": pub, "summary": summary[:200]})

    return items[:10]


def fetch_market_news(max_per_source: int = 5) -> list[dict]:
    all_news = []
    for source, url in RSS_FEEDS.items():
        items = _parse_rss(url)
        for item in items[:max_per_source]:
            item["source"] = source
            all_news.append(item)
    return all_news


def score_macro_relevance(title: str, summary: str = "") -> int:
    text = (title + " " + summary).lower()
    return sum(1 for kw in MACRO_KEYWORDS if kw.lower() in text)
