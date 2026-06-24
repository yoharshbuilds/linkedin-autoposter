"""Test harness: search news and rank it 'like Rahul Mathur' using the learned rubric.

Run: python src/scout.py
Prints the candidate news, each scored 0-10 with the angle Rahul would take and the image template.
Does NOT generate or post anything. This is the "can it pick news like Rahul" test.
"""
import os
import sys
import json

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import research
import llm

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _load_env():
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _cfg():
    return yaml.safe_load(open(os.path.join(ROOT, "config.yaml")))


def score_candidates(items: list, cfg: dict, top_n: int = 12, recent_titles: list = None) -> list:
    rubric = open(os.path.join(ROOT, "reference", "news_taste.md")).read()
    items = items[:25]
    listing = "\n".join(
        f"[{i}] ({c.get('source','')}) {c.get('title','')} :: {c.get('summary','')[:160]}"
        for i, c in enumerate(items)
    )
    already = ""
    if recent_titles:
        already = ("\n\nALREADY POSTED RECENTLY (give score 0 to any candidate that is the SAME "
                   "underlying story as any of these, even if worded differently / different source):\n"
                   + "\n".join(f"- {t}" for t in recent_titles) + "\n")
    prompt = (
        f"{rubric}\n{already}\n"
        f"CANDIDATE NEWS ITEMS:\n{listing}\n\n"
        "Score EACH item the way Rahul Mathur would, using the rubric. Return STRICT JSON: "
        '{\"picks\":[{\"i\":<index>,\"score\":<0-10>,\"angle\":\"the one-line angle Rahul would take\",'
        '\"template\":\"returns_table|bar_chart|calc_worksheet|app_showdown|tweet_card|photo|thesis_card|none\"}]} '
        "Include ALL items, sorted by score descending."
    )
    raw = llm.chat(cfg["text_model"], [
        {"role": "system", "content": "You are Rahul Mathur's editorial filter. Be selective and specific."},
        {"role": "user", "content": prompt},
    ], temperature=0.3)
    raw = raw.strip()
    if raw.startswith("```"):
        import re
        raw = re.sub(r"^```[a-z]*\n?|\n?```$", "", raw).strip()
    picks = json.loads(raw)["picks"]
    for p in picks:
        p["item"] = items[p["i"]] if 0 <= p["i"] < len(items) else {}
    return picks[:top_n]


def main():
    _load_env()
    cfg = _cfg()
    print("Searching news across his beats...\n")
    items = research.gather(cfg)
    print(f"{len(items)} candidates found. Scoring like Rahul...\n")
    picks = score_candidates(items, cfg)
    print("=" * 72)
    print("WOULD RAHUL POST THIS? (ranked)")
    print("=" * 72)
    for p in picks:
        it = p["item"]
        flag = "POST" if p["score"] >= 7 else "skip"
        age = it.get("age_hours")
        age_s = f"{age}h ago" if age is not None else "undated"
        print(f"\n[{p['score']}/10 {flag}] {it.get('title','')[:90]}")
        print(f"   source: {it.get('source','')}  ({it.get('via','')})  | {age_s}")
        print(f"   angle : {p['angle']}")
        print(f"   image : {p['template']}")


if __name__ == "__main__":
    main()
