"""Orchestrate: research -> pick fresh item -> generate post -> stat-card -> publish."""
import os
import sys
import json
import datetime

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import research
import generate
import scout
import card
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


def run():
    load_env()
    cfg = load_cfg()
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M}] gathering news...")
    candidates = research.gather(cfg)
    fresh = [c for c in candidates if not state.seen(c)]
    print(f"  {len(candidates)} candidates, {len(fresh)} fresh")
    if not fresh:
        print("  nothing new to post. done.")
        return

    # rank like Rahul (rubric), pick the highest-scoring fresh item
    angle, template_hint = "", ""
    try:
        picks = scout.score_candidates(fresh, cfg, recent_titles=state.recent_titles())
        picks = [p for p in picks if p.get("item")]
        best = max(picks, key=lambda p: p.get("score", 0)) if picks else None
        min_score = cfg.get("min_score", 6)
        if best and best.get("score", 0) >= min_score:
            item = best["item"]; angle = best.get("angle", ""); template_hint = best.get("template", "")
            print(f"  chosen [{best['score']}/10]: {item['title'][:80]}  ({item['source']})")
            print(f"  angle: {angle}")
        else:
            top = best['score'] if best else 'n/a'
            print(f"  no fresh item scored >= {min_score} (top={top}). skipping this run.")
            return
    except Exception as e:
        print(f"  [warn] scoring failed ({e}); falling back to freshest")
        item = fresh[0]

    data = generate.generate(item, cfg, angle=angle, template_hint=template_hint)
    post_text = data["post_text"]
    print("\n----- POST -----\n" + post_text + "\n----------------\n")

    out_dir = os.path.join(ROOT, "out")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    img_path = os.path.join(out_dir, f"card-{stamp}.png")
    img = data.get("image", {}) or {}
    template = img.get("template", "thesis_card")
    img.setdefault("attribution",
                   f"created by @{os.environ.get('MY_HANDLE','harshshah')} | retrieved {datetime.date.today():%d %b %Y}")
    try:
        card.render(template, img, img_path)
        print(f"  image [{template}]: {img_path}")
    except Exception as e:
        print(f"  [warn] image render failed: {e}")
        img_path = ""

    content = {"post_text": post_text, "tweet_text": data.get("tweet_text", post_text), "image": img_path}
    results = post_mod.publish(content, cfg)
    ok_any = False
    for r in results:
        ok_any = ok_any or r["ok"]
        print(f"  {r['target']} [{r['mode']}]: {'OK' if r['ok'] else 'FAILED'} - {r['detail']}")

    if ok_any:
        state.record(item, post_text, img_path, datetime.datetime.now(datetime.timezone.utc).isoformat())
        print("  recorded in state.")


if __name__ == "__main__":
    run()
