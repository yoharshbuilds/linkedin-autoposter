"""Orchestrate: research -> pick fresh item -> generate post -> stat-card -> publish."""
import os
import sys
import json
import datetime

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import research
import enrich
import generate
import scout
import card
import media
import post as post_mod
import state

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")


def load_env():
    """Load KEY=VALUE pairs from .env into os.environ (no external dep)."""
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def load_cfg():
    with open(os.path.join(ROOT, "config.yaml")) as f:
        return yaml.safe_load(f)


DATA_CARDS = {"returns_table", "bar_chart", "calc_worksheet", "app_showdown",
              "tweet_card", "thesis_card"}


def _thesis_fallback(item: dict, img: dict, out_dir: str, stamp: str) -> str:
    """Last-resort card built from whatever we have, so a post always has an image."""
    path = os.path.join(out_dir, f"card-{stamp}.png")
    data = {
        "title": (img.get("title") or item.get("title", ""))[:90],
        "stat": img.get("stat", ""),
        "subtext": img.get("subtext") or item.get("source", ""),
        "attribution": img.get("attribution", ""),
    }
    try:
        return card.render("thesis_card", data, path)
    except Exception as e:
        print(f"  [warn] thesis fallback failed: {e}")
        return ""


def _framed_photo(real_path: str, item: dict, img: dict, out_dir: str, stamp: str) -> str:
    """Wrap a found image in a LinkedIn-perfect 4:5 frame with a readable headline + source band.

    Falls back to the raw image if framing fails, so we never lose a usable creative.
    """
    out = os.path.join(out_dir, f"card-{stamp}.png")
    headline = (img.get("headline") or item.get("title") or "").strip()
    src = (item.get("source") or "").lstrip("@")
    kicker = (img.get("kicker") or src or "NEWS").upper()
    try:
        data = {
            "image": media.to_data_uri(real_path),
            "headline": headline,
            "kicker": kicker,
            "attribution": img.get("attribution", ""),
        }
        card.render("photo_frame", data, out)
        print(f"  image [photo_frame]: {out}  (source: {real_path})")
        return out
    except Exception as e:
        print(f"  [warn] framing failed ({e}); using raw source image")
        return real_path


def _make_image(template: str, img: dict, item: dict, out_dir: str, stamp: str, cfg: dict) -> str:
    """Route to the right image source: his data card, the real source creative, or a fallback.

    Order of preference honors what the editorial filter chose, but always degrades
    gracefully so a post never goes out without an image.
    """
    use_real = cfg.get("use_source_images", True)
    path = os.path.join(out_dir, f"card-{stamp}.png")

    # tweet_card with no quoted text but a source tweet -> fill from the item
    if template == "tweet_card" and not img.get("text") and item.get("tweet"):
        img.update({k: item["tweet"].get(k, "") for k in ("name", "handle", "text")})

    # 1. story is visual: use the real source creative, wrapped in a clean frame
    if template in ("photo", "none", "") and use_real:
        real = media.fetch_source_image(item, os.path.join(out_dir, f"src-{stamp}"))
        if real:
            return _framed_photo(real, item, img, out_dir, stamp)
        print("  [info] no source creative found; using thesis card")
        return _thesis_fallback(item, img, out_dir, stamp)

    # 2. his data card
    if template in DATA_CARDS:
        try:
            card.render(template, img, path)
            print(f"  image [{template}]: {path}")
            return path
        except Exception as e:
            print(f"  [warn] {template} render failed: {e}; trying source creative")

    # 3. data card failed or unknown template: try the real creative (framed), then thesis
    if use_real:
        real = media.fetch_source_image(item, os.path.join(out_dir, f"src-{stamp}"))
        if real:
            return _framed_photo(real, item, img, out_dir, stamp)
    return _thesis_fallback(item, img, out_dir, stamp)


def run():
    load_env()
    cfg = load_cfg()
    # env override: DRY_RUN=1 forces a no-post validation run regardless of config
    if os.environ.get("DRY_RUN") in ("1", "true", "True"):
        cfg["dry_run"] = True
    # go-live gate: stay in preview mode until live_from date (inclusive)
    live_from = cfg.get("live_from")
    if live_from and str(datetime.date.today()) < str(live_from) and not cfg.get("dry_run"):
        cfg["dry_run"] = True
        print(f"  [gate] before live_from={live_from}; running as preview (no post).")
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M}] gathering news... (dry_run={cfg.get('dry_run')})")
    candidates = research.gather(cfg)
    fresh = [c for c in candidates if not state.seen(c)]
    print(f"  {len(candidates)} candidates, {len(fresh)} fresh")
    if not fresh:
        print("  nothing new to post. done.")
        return

    # rank like Rahul (rubric)
    min_score = cfg.get("min_score", 6)
    try:
        picks = scout.score_candidates(fresh, cfg, recent_titles=state.recent_titles())
        picks = [p for p in picks if p.get("item") and p.get("score", 0) >= min_score]
        picks.sort(key=lambda p: p.get("score", 0), reverse=True)
    except Exception as e:
        print(f"  [warn] scoring failed ({e}); falling back to freshest")
        picks = [{"item": c, "score": 0, "angle": "", "template": ""} for c in fresh[:4]]
    if not picks:
        print(f"  no fresh item scored >= {min_score}. skipping this run.")
        return

    # research each candidate (in score order) and take the first whose UNDERLYING EVENT is recent.
    # this catches freshly-published analysis/roundup pieces about old deals (article is new, news is not).
    item = None; angle = ""; template_hint = ""; fact_block = ""
    max_days = cfg.get("event_recency_days", 4)
    for cand in picks[: cfg.get("research_candidates", 4)]:
        it = cand["item"]
        print(f"  candidate [{cand.get('score','?')}/10]: {it['title'][:80]}  ({it['source']})")
        try:
            rsrch = enrich.research(it, cfg)
        except Exception as e:
            print(f"  [warn] research failed ({e}); proceeding without event gate")
            rsrch = {}
        age = enrich.event_age_days(rsrch)
        if age is not None and age > max_days:
            print(f"  [stale] event ~{age}d ago ({rsrch.get('event_date')}) > {max_days}d. skipping.")
            state.mark_seen(it, reason=f"stale-event-{age}d")  # don't re-research next run
            continue
        item = it; angle = cand.get("angle", ""); template_hint = cand.get("template", "")
        fact_block = enrich.factsheet_text(rsrch)
        ev = rsrch.get("event_date", "?")
        extra = (", computed " + ", ".join(c["metric"] for c in rsrch["computed"])) if rsrch.get("computed") else ""
        print(f"  chosen: event {ev} (~{age}d), {len(rsrch.get('facts',[]))} facts{extra}")
        print(f"  angle: {angle}")
        break

    if item is None:
        print("  all top candidates were stale events. skipping this run.")
        return

    data = generate.generate(item, cfg, angle=angle, template_hint=template_hint, facts=fact_block)
    post_text = data["post_text"]
    print("\n----- POST -----\n" + post_text + "\n----------------\n")

    out_dir = os.path.join(ROOT, "out")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    img_path = os.path.join(out_dir, f"card-{stamp}.png")
    img = data.get("image", {}) or {}
    template = img.get("template", "thesis_card")
    img.setdefault("attribution",
                   f"created by @{os.environ.get('MY_HANDLE','harshshah')} | retrieved {datetime.date.today():%d %b %Y}")

    img_path = _make_image(template, img, item, out_dir, stamp, cfg)

    content = {"post_text": post_text, "tweet_text": data.get("tweet_text", post_text), "image": img_path}
    results = post_mod.publish(content, cfg)
    ok_any = False
    for r in results:
        ok_any = ok_any or r["ok"]
        print(f"  {r['target']} [{r['mode']}]: {'OK' if r['ok'] else 'FAILED'} - {r['detail']}")

    if ok_any and not cfg.get("dry_run"):
        state.record(item, post_text, img_path, datetime.datetime.now(datetime.timezone.utc).isoformat())
        print("  recorded in state.")
    elif cfg.get("dry_run"):
        print("  dry run: not recorded (live run can still post this).")


if __name__ == "__main__":
    run()
