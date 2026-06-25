"""Dedupe store so we never post the same news item twice."""
import json
import os
import hashlib

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "state", "posted.json")


def _load() -> dict:
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"posted": []}


def item_key(item: dict) -> str:
    """Stable key for an item, based on url or title."""
    basis = (item.get("url") or item.get("title") or item.get("text") or "").strip().lower()
    return hashlib.sha1(basis.encode()).hexdigest()[:16]


def _norm(s: str) -> set:
    import re
    words = re.findall(r"[a-z0-9]+", (s or "").lower())
    stop = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "is", "as", "at", "by", "with"}
    return {w for w in words if w not in stop and len(w) > 2}


def seen(item: dict, sim_threshold: float = 0.6) -> bool:
    """True if this exact item, OR a near-duplicate story, was already posted.

    Exact match is by url/title hash. Near-duplicate is Jaccard word overlap of the title
    against previously posted titles, so we never post the same story twice even from a
    different source/url.
    """
    posted = _load()["posted"]
    keys = {p["key"] for p in posted}
    if item_key(item) in keys:
        return True
    title_words = _norm(item.get("title") or item.get("text", ""))
    if not title_words:
        return False
    for p in posted:
        prev = _norm(p.get("title", ""))
        if not prev:
            continue
        overlap = len(title_words & prev) / len(title_words | prev)
        if overlap >= sim_threshold:
            return True
    return False


def recent_titles(n: int = 20) -> list:
    """Titles of the most recently posted stories (for same-story dedup)."""
    posted = _load()["posted"]
    return [p.get("title", "") for p in posted[-n:] if p.get("title")]


def mark_seen(item: dict, reason: str = "skipped") -> None:
    """Remember an item we deliberately skipped (e.g. stale event) so we never re-pick or re-research it."""
    state = _load()
    state["posted"].append({
        "key": item_key(item),
        "title": item.get("title") or item.get("text", "")[:120],
        "url": item.get("url"),
        "skipped": reason,
    })
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def record(item: dict, post_text: str, image_path: str, posted_at: str) -> None:
    state = _load()
    state["posted"].append({
        "key": item_key(item),
        "title": item.get("title") or item.get("text", "")[:120],
        "url": item.get("url"),
        "posted_at": posted_at,
        "image": image_path,
    })
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
