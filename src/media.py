"""Found-image pipeline: grab the source's real creative when the story is visual.

Rahul attaches real imagery (founder photos, product shots, brand heroes, podcast
stills, tweet screenshots) when a story is better shown than charted. This module
pulls that creative for the chosen item:
  1. item['image_url'] if research already captured one (RSS media / tweet media)
  2. else the article's og:image / twitter:image
  3. else the first sizeable <img> in the page
Returns a local file path, or "" if nothing usable was found. Always best-effort:
callers fall back to a data card on "".
"""
import base64
import os
import re

import requests


def to_data_uri(path: str) -> str:
    """Read a local image file into a base64 data URI (for embedding in the frame template)."""
    ext = os.path.splitext(path)[1].lower().lstrip(".") or "jpeg"
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    with open(path, "rb") as f:
        return f"data:image/{mime};base64," + base64.b64encode(f.read()).decode()

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
_MIN_BYTES = 8000  # skip tracking pixels / tiny logos


def _download(url: str, out_path: str) -> str:
    try:
        r = requests.get(url, headers=_UA, timeout=25, stream=True)
        r.raise_for_status()
        ctype = r.headers.get("Content-Type", "")
        if "image" not in ctype and not re.search(r"\.(png|jpe?g|webp)(\?|$)", url, re.I):
            return ""
        data = r.content
        if len(data) < _MIN_BYTES:
            return ""
        ext = ".png" if "png" in ctype or url.lower().endswith(".png") else ".jpg"
        path = out_path if out_path.lower().endswith((".png", ".jpg", ".jpeg")) else out_path + ext
        with open(path, "wb") as f:
            f.write(data)
        return path
    except Exception:
        return ""


def _og_image(page_url: str) -> str:
    try:
        r = requests.get(page_url, headers=_UA, timeout=20)
        html = r.text
    except Exception:
        return ""
    for pat in (
        r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    ):
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1).strip()
    # last resort: first big-looking <img>
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+\.(?:png|jpe?g|webp)[^"\']*)["\']', html, re.I):
        src = m.group(1)
        if "logo" not in src.lower() and "icon" not in src.lower():
            return src
    return ""


def fetch_source_image(item: dict, out_path: str) -> str:
    """Return a local path to the source's real creative, or '' if none usable."""
    # 1. image_url captured at research time (RSS media / tweet media)
    url = (item.get("image_url") or "").strip()
    if url:
        p = _download(url, out_path)
        if p:
            return p
    # 2. og:image from the article / tweet page
    page = (item.get("url") or "").strip()
    if page.startswith("http"):
        og = _og_image(page)
        if og:
            if og.startswith("//"):
                og = "https:" + og
            p = _download(og, out_path)
            if p:
                return p
    return ""
