"""Find fresh, on-topic news items via RSS (reliable) + twitter-cli (optional)."""
import json
import re
import subprocess
import time
from datetime import datetime, timezone, timedelta

import feedparser
import requests


def _age_hours(dt: datetime) -> float:
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0


def _parse_twitter_date(p: dict):
    """Return a tz-aware datetime for a tweet, or None."""
    iso = p.get("createdAtISO")
    if iso:
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except ValueError:
            pass
    raw = p.get("createdAt")
    if raw:
        try:  # Twitter format: 'Sun Mar 29 11:18:34 +0000 2015'
            return datetime.strptime(raw, "%a %b %d %H:%M:%S %z %Y")
        except ValueError:
            pass
    return None


def _within(dt, cfg: dict) -> bool:
    """Hard recency gate. Drops undated items when strict_recency is on."""
    if dt is None:
        return not cfg.get("strict_recency", True)
    return _age_hours(dt) <= cfg["recency_hours"]


def _matches(text: str, keywords: list) -> bool:
    t = text.lower()
    return any(k.lower() in t for k in keywords)


# digest / roundup / opinion pieces revisit OLD events even when freshly published. Drop them.
_DIGEST = re.compile(
    r"(&|and)\s+more\b|round[\s-]?up|weekly|daily digest|this week|funding galore|"
    r"top \d+|in \d+ charts|newsletter|recap|wrapped|year in review|explained|"
    r"\bhow\b.*\bbuilt\b|deep dive|throwback",
    re.I,
)


def _is_digest(title: str) -> bool:
    return bool(_DIGEST.search(title or ""))


def from_rss(cfg: dict) -> list:
    items = []
    for url in cfg.get("rss_feeds", []):
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            feed = feedparser.parse(resp.content)
        except Exception:
            continue
        source = feed.feed.get("title", url)
        for e in feed.entries[:25]:
            st = e.get("published_parsed") or e.get("updated_parsed")
            dt = datetime.fromtimestamp(time.mktime(st), tz=timezone.utc) if st else None
            if not _within(dt, cfg):
                continue
            title = e.get("title", "").strip()
            if _is_digest(title):
                continue
            blob = f"{title} {e.get('summary','')}"
            if not _matches(blob, cfg["keywords"]):
                continue
            items.append({
                "title": title,
                "summary": _clean(e.get("summary", "")),
                "url": e.get("link"),
                "source": source,
                "via": "rss",
                "image_url": _rss_image(e),
                "published": dt.isoformat() if dt else None,
                "age_hours": round(_age_hours(dt), 1) if dt else None,
            })
    return items


def _clean(html: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", html or "").strip()[:600]


def _rss_image(e: dict) -> str:
    """Best-effort lead image from a feed entry (media:content / thumbnail / enclosure / <img>)."""
    import re
    for m in (e.get("media_content") or []):
        if m.get("url"):
            return m["url"]
    for m in (e.get("media_thumbnail") or []):
        if m.get("url"):
            return m["url"]
    for l in (e.get("links") or []):
        if l.get("rel") == "enclosure" and (l.get("type", "").startswith("image")):
            return l.get("href", "")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', e.get("summary", "") or "")
    return m.group(1) if m else ""


def from_twitter(cfg: dict) -> list:
    """Pull recent tweets from configured ecosystem accounts. Best-effort."""
    if not cfg.get("use_twitter_research"):
        return []
    items = []
    for handle in cfg.get("twitter_sources", []):
        try:
            out = subprocess.run(
                ["twitter", "user-posts", handle, "-n", "15", "--json"],
                capture_output=True, text=True, timeout=60,
            )
            if out.returncode != 0:
                continue
            parsed = json.loads(out.stdout)
            posts = parsed.get("data", []) if isinstance(parsed, dict) else parsed
        except Exception:
            continue
        for p in posts:
            if p.get("isRetweet"):
                continue
            dt = _parse_twitter_date(p)
            if not _within(dt, cfg):
                continue
            text = p.get("text", "")
            if not _matches(text, cfg["keywords"]):
                continue
            photo = next((m.get("url") for m in (p.get("media") or [])
                          if m.get("type") == "photo" and m.get("url")), "")
            items.append({
                "title": text[:120],
                "summary": text,
                "url": f"https://x.com/{handle}/status/{p.get('id')}",
                "source": f"@{handle}",
                "via": "twitter",
                "image_url": photo,
                "tweet": {"name": handle, "handle": handle, "text": text},
                "views": (p.get("metrics") or {}).get("views", 0),
                "published": dt.isoformat() if dt else None,
                "age_hours": round(_age_hours(dt), 1) if dt else None,
            })
    return items


def gather(cfg: dict) -> list:
    """Return candidate items within the recency window, freshest first."""
    items = from_rss(cfg) + from_twitter(cfg)
    # latest-news rule: sort by age ascending (most recent first); undated last
    items.sort(key=lambda x: (x.get("age_hours") is None, x.get("age_hours", 1e9)))
    return items
