"""Publish to LinkedIn and/or Twitter. DRY_RUN saves previews instead of posting.

- Twitter: uses the locally-authenticated twitter-cli session (no extra key). Non-premium
  accounts cap at 280 chars, so we post the short tweet_text + the stat-card image.
- LinkedIn: no public posting API for individuals, so we automate the web UI with Playwright
  and your li_at cookie. This is against LinkedIn ToS and carries account risk. Keep DRY_RUN on
  until you have reviewed output, and prefer a stable residential IP.
"""
import os
import json
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


def _playwright_post(post_text, image_path, cfg):
    """Publish via the dedicated, persistently-logged-in Chrome profile (trusted session)."""
    from playwright.sync_api import sync_playwright
    profile = os.path.abspath(LI_PROFILE)
    headless = cfg.get("headless", False)  # headful is more reliable / lower flag risk
    launch = dict(user_data_dir=profile, headless=headless, viewport={"width": 1300, "height": 950},
                  args=["--disable-blink-features=AutomationControlled"])
    with sync_playwright() as pw:
        try:
            ctx = pw.chromium.launch_persistent_context(channel="chrome", **launch)
        except Exception:
            ctx = pw.chromium.launch_persistent_context(**launch)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.linkedin.com/feed/", wait_until="load")
        page.wait_for_timeout(7000)
        if "login" in page.url or "checkpoint" in page.url or "authwall" in page.url:
            ctx.close()
            return {"target": "linkedin", "mode": "live", "ok": False,
                    "detail": f"session expired ({page.url}); rerun the one-time login"}
        # open composer (button ancestor of the 'Start a post' text)
        page.get_by_text("Start a post", exact=False).first.locator(
            'xpath=ancestor-or-self::*[self::button or @role="button"][1]').click(timeout=12000)
        page.wait_for_timeout(3000)
        ed = page.locator('.ql-editor, div[role="textbox"][contenteditable="true"]').first
        ed.click()
        page.keyboard.insert_text(post_text)
        page.wait_for_timeout(1200)
        if image_path and os.path.exists(image_path):
            try:
                with page.expect_file_chooser(timeout=9000) as fc:
                    page.locator('div[role=dialog] button[aria-label="Add media"]').first.click()
                fc.value.set_files(image_path)
                page.wait_for_timeout(3500)
                for _ in range(2):  # advance media editor if it shows "Next"
                    nx = page.locator('div[role=dialog] button:has-text("Next")').first
                    if nx.count() and nx.is_visible():
                        nx.click(); page.wait_for_timeout(2000)
                    else:
                        break
            except Exception as e:
                print(f"[warn] LI image attach failed, posting text only: {e}")
        # primary publish button = exact name 'Post' (avoids 'Post to Anyone')
        target = None
        pb = page.get_by_role("button", name="Post", exact=True)
        for i in range(pb.count()):
            b = pb.nth(i)
            if b.is_visible() and b.is_enabled():
                target = b
        if not target:
            ctx.close()
            return {"target": "linkedin", "mode": "live", "ok": False, "detail": "no enabled Post button"}
        target.click()
        page.wait_for_timeout(7000)
        ok = page.locator('.ql-editor').count() == 0  # composer closed => published
        ctx.close()
        return {"target": "linkedin", "mode": "live", "ok": ok,
                "detail": "posted" if ok else "composer still open (post may not have sent)"}


# ---------------- dispatcher ----------------

def publish(content: dict, cfg: dict) -> list:
    """content = {post_text, tweet_text, image}. Posts to each target in cfg['post_targets']."""
    targets = cfg.get("post_targets", ["linkedin"])
    results = []
    if "linkedin" in targets:
        results.append(post_linkedin(content["post_text"], content.get("image", ""), cfg))
    if "twitter" in targets:
        tweet = content.get("tweet_text") or content["post_text"]
        results.append(post_twitter(tweet, content.get("image", ""), cfg))
    return results
