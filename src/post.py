"""Publish to LinkedIn and/or Twitter. DRY_RUN saves previews instead of posting.

- Twitter: uses the locally-authenticated twitter-cli session (no extra key). Non-premium
  accounts cap at 280 chars, so we post the short tweet_text + the stat-card image.
- LinkedIn: no public posting API for individuals, so we automate the web UI with Playwright
  and your li_at cookie. This is against LinkedIn ToS and carries account risk. Keep DRY_RUN on
  until you have reviewed output, and prefer a stable residential IP.
"""
import os
import json
import re
import subprocess
import datetime


def _stamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _out_dir():
    return os.path.join(os.path.dirname(__file__), "..", "out")


# ---------------- Twitter ----------------

def post_twitter(tweet_text: str, image_path: str, cfg: dict) -> dict:
    limit = cfg.get("twitter_max_chars", 280)
    text = tweet_text.strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    if cfg.get("dry_run", True):
        path = os.path.join(_out_dir(), f"tweet-preview-{_stamp()}.txt")
        os.makedirs(_out_dir(), exist_ok=True)
        open(path, "w").write(text + f"\n\n[image: {image_path}]\n")
        return {"target": "twitter", "mode": "dry", "ok": True, "detail": f"preview: {path}"}
    cmd = ["twitter", "post", text]
    if image_path and os.path.exists(image_path):
        cmd += ["--image", image_path]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        ok = r.returncode == 0
        return {"target": "twitter", "mode": "live", "ok": ok,
                "detail": (r.stdout or r.stderr).strip()[:200]}
    except Exception as e:
        return {"target": "twitter", "mode": "live", "ok": False, "detail": str(e)}


# ---------------- LinkedIn ----------------

LI_PROFILE = os.path.join(os.path.dirname(__file__), "..", ".li-profile")


def post_linkedin(post_text: str, image_path: str, cfg: dict) -> dict:
    if cfg.get("dry_run", True):
        path = os.path.join(_out_dir(), f"li-preview-{_stamp()}.txt")
        os.makedirs(_out_dir(), exist_ok=True)
        open(path, "w").write(post_text + f"\n\n[image: {image_path}]\n")
        return {"target": "linkedin", "mode": "dry", "ok": True, "detail": f"preview: {path}"}
    if not os.path.isdir(LI_PROFILE):
        return {"target": "linkedin", "mode": "live", "ok": False,
                "detail": "no .li-profile (run the one-time login first)"}
    try:
        return _playwright_post(post_text, image_path, cfg)
    except Exception as e:
        return {"target": "linkedin", "mode": "live", "ok": False, "detail": f"playwright error: {e}"}


_EDITOR = '.ql-editor, div[role="textbox"][contenteditable="true"]'


def _save_debug(page, tag: str) -> str:
    """Screenshot + a slice of DOM on failure, so a future LinkedIn UI change is diagnosable."""
    try:
        os.makedirs(_out_dir(), exist_ok=True)
        shot = os.path.join(_out_dir(), f"li-fail-{tag}-{_stamp()}.png")
        page.screenshot(path=shot)
        return shot
    except Exception:
        return ""


def _first_visible(page, locator):
    """Return the first visible+enabled element of a locator, or None."""
    try:
        n = locator.count()
    except Exception:
        return None
    for i in range(n):
        el = locator.nth(i)
        try:
            if el.is_visible() and el.is_enabled():
                return el
        except Exception:
            continue
    return None


def _open_composer(page) -> bool:
    """Open the 'Start a post' composer, robust to LinkedIn markup changes."""
    page.wait_for_timeout(1500)
    strategies = [
        lambda: page.locator('div[aria-label="Start a post"]'),
        lambda: page.locator('button[aria-label="Start a post"]'),
        lambda: page.locator('button:has-text("Start a post")'),
        lambda: page.locator('.share-box-feed-entry__trigger'),
        lambda: page.get_by_role("button", name="Start a post"),
        lambda: page.get_by_text("Start a post", exact=False).first.locator(
            'xpath=ancestor-or-self::*[self::button or @role="button" or @aria-label][1]'),
    ]
    for make in strategies:
        try:
            trigger = make()
            if not trigger.count():
                continue
            el = _first_visible(page, trigger) or trigger.first
            el.scroll_into_view_if_needed(timeout=4000)
            el.click(timeout=8000)
            page.wait_for_selector(_EDITOR, state="visible", timeout=8000)
            return True
        except Exception:
            continue
    return False


def _attach_image(page, image_path: str) -> bool:
    """Attach an image. Tries the hidden file input directly, then the add-media button chooser."""
    if not (image_path and os.path.exists(image_path)):
        return True  # nothing to attach is not a failure
    # strategy A: set the hidden <input type=file> directly (most robust, no chooser dialog)
    try:
        inp = page.locator('input[type="file"]')
        if inp.count():
            inp.first.set_input_files(image_path)
            page.wait_for_timeout(3500)
            _advance_next(page)
            return True
    except Exception:
        pass
    # strategy B: click an add-media button and catch the OS file chooser
    for sel in ('div[role=dialog] button[aria-label="Add media"]',
                'button[aria-label="Add a photo"]',
                'button[aria-label*="media" i]',
                'button[aria-label*="photo" i]'):
        try:
            btn = _first_visible(page, page.locator(sel))
            if not btn:
                continue
            with page.expect_file_chooser(timeout=9000) as fc:
                btn.click()
            fc.value.set_files(image_path)
            page.wait_for_timeout(3500)
            _advance_next(page)
            return True
        except Exception:
            continue
    return False


def _advance_next(page):
    """Click through any 'Next' step in the media editor back to the main composer."""
    for _ in range(3):
        nx = _first_visible(page, page.locator('div[role=dialog] button:has-text("Next")'))
        if not nx:
            return
        try:
            nx.click(); page.wait_for_timeout(1800)
        except Exception:
            return


def _click_post(page) -> bool:
    """Click the primary publish button (exact 'Post', never 'Post to Anyone')."""
    for make in (
        lambda: page.get_by_role("button", name="Post", exact=True),
        lambda: page.locator('div[role=dialog] button.share-actions__primary-action'),
        lambda: page.locator('button:has-text("Post")'),
    ):
        try:
            btn = _first_visible(page, make())
        except Exception:
            btn = None
        if btn:
            try:
                btn.click(); return True
            except Exception:
                continue
    return False


def _attempt(pw, post_text, image_path, cfg) -> dict:
    profile = os.path.abspath(LI_PROFILE)
    launch = dict(user_data_dir=profile, headless=cfg.get("headless", False),
                  viewport={"width": 1300, "height": 950},
                  args=["--disable-blink-features=AutomationControlled"])
    try:
        ctx = pw.chromium.launch_persistent_context(channel="chrome", **launch)
    except Exception:
        ctx = pw.chromium.launch_persistent_context(**launch)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(6000)
        if any(x in page.url for x in ("/login", "/checkpoint", "/authwall", "/uas/")):
            return {"target": "linkedin", "mode": "live", "ok": False,
                    "detail": f"session expired ({page.url}); rerun the one-time login"}
        if not _open_composer(page):
            return {"target": "linkedin", "mode": "live", "ok": False,
                    "detail": f"could not open composer (markup changed?); debug: {_save_debug(page,'composer')}"}
        ed = page.locator(_EDITOR).first
        ed.click()
        page.keyboard.insert_text(post_text)
        page.wait_for_timeout(1200)
        img_note = ""
        if not _attach_image(page, image_path):
            img_note = " (image attach failed, posted text only)"
            print(f"  [warn] LI image attach failed; debug: {_save_debug(page,'image')}")
        if not _click_post(page):
            return {"target": "linkedin", "mode": "live", "ok": False,
                    "detail": f"no enabled Post button; debug: {_save_debug(page,'postbtn')}"}
        # verify the composer actually closed (= published)
        try:
            page.wait_for_selector(_EDITOR, state="detached", timeout=12000)
            ok = True
        except Exception:
            ok = page.locator(_EDITOR).count() == 0
        if not ok:
            _save_debug(page, "verify")
        return {"target": "linkedin", "mode": "live", "ok": ok,
                "detail": ("posted" + img_note) if ok else "composer still open (post may not have sent)"}
    finally:
        try:
            ctx.close()
        except Exception:
            pass


def _playwright_post(post_text, image_path, cfg):
    """Publish via the persistently-logged-in Chrome profile. Retries once on failure."""
    from playwright.sync_api import sync_playwright
    attempts = int(cfg.get("li_attempts", 2))
    last = {"target": "linkedin", "mode": "live", "ok": False, "detail": "no attempt made"}
    for i in range(attempts):
        with sync_playwright() as pw:
            try:
                last = _attempt(pw, post_text, image_path, cfg)
            except Exception as e:
                last = {"target": "linkedin", "mode": "live", "ok": False, "detail": f"exception: {e}"}
        if last.get("ok"):
            if i:
                last["detail"] += f" (on retry {i+1})"
            return last
        if i + 1 < attempts:
            print(f"  [retry] LinkedIn attempt {i+1} failed: {last['detail']}")
    return last


# ---------------- dispatcher ----------------

def publish(content: dict, cfg: dict) -> list:
    """content = {post_text, tweet_text, image}. Posts to all targets SIMULTANEOUSLY.

    LinkedIn (Playwright) and Twitter (twitter-cli) are independent subsystems, so we
    fire them in parallel threads to publish at the same moment instead of one after
    the other.
    """
    import threading

    targets = cfg.get("post_targets", ["linkedin"])
    jobs = []
    if "linkedin" in targets:
        jobs.append(("linkedin", lambda: post_linkedin(content["post_text"], content.get("image", ""), cfg)))
    if "twitter" in targets:
        tweet = content.get("tweet_text") or content["post_text"]
        jobs.append(("twitter", lambda: post_twitter(tweet, content.get("image", ""), cfg)))

    results = [None] * len(jobs)

    def _run(i, fn, name):
        try:
            results[i] = fn()
        except Exception as e:
            results[i] = {"target": name, "mode": "live", "ok": False, "detail": f"crashed: {e}"}

    threads = [threading.Thread(target=_run, args=(i, fn, name)) for i, (name, fn) in enumerate(jobs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results
