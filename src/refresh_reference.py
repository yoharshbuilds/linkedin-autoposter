"""Re-pull Rahul's latest posts and rebuild the style few-shot from his last 50.

Run: python src/refresh_reference.py [N]   (default N=50)
Writes reference/rahul_last50.json (clean corpus) and reference/rahul_fewshot.json
(the best ~15 substantive, high-engagement posts that generate.py learns from).
Keeps the style tuned to how he writes RIGHT NOW, not months ago.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
REF = os.path.join(ROOT, "reference")
HANDLE = "Rahul_J_Mathur"


def fetch(n_fetch: int = 80) -> list:
    out = subprocess.run(
        ["twitter", "user-posts", HANDLE, "-n", str(n_fetch), "--json"],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        raise SystemExit(f"twitter-cli failed: {out.stderr[:300]}")
    parsed = json.loads(out.stdout)
    return parsed.get("data", []) if isinstance(parsed, dict) else parsed


def clean(p: dict) -> dict:
    m = p.get("metrics") or {}
    return {
        "text": (p.get("text") or "").strip(),
        "createdAt": p.get("createdAtISO") or p.get("createdAt"),
        "likes": m.get("likes", 0),
        "retweets": m.get("retweets", 0),
        "bookmarks": m.get("bookmarks", 0),
        "replies": m.get("replies", 0),
        "views": m.get("views", 0),
        "has_media": bool(p.get("media")),
        "url": f"https://x.com/{HANDLE}/status/{p.get('id')}",
    }


def score(c: dict) -> int:
    return c["likes"] + 2 * c["retweets"] + 2 * c["bookmarks"] + c["replies"]


def main(n: int = 50):
    arr = fetch(max(80, n + 25))
    orig = [p for p in arr
            if not p.get("isRetweet")
            and (p.get("text") or "").strip()
            and not (p.get("text") or "").lstrip().startswith("@")]
    if len(orig) < n:
        print(f"  [warn] only {len(orig)} original posts available (< {n})")
    last_n = [clean(p) for p in orig[:n]]
    json.dump(last_n, open(os.path.join(REF, "rahul_last50.json"), "w"),
              indent=2, ensure_ascii=False)

    substantive = sorted([c for c in last_n if len(c["text"]) >= 220],
                         key=score, reverse=True)
    fewshot = substantive[:15] if len(substantive) >= 15 else \
        sorted(last_n, key=score, reverse=True)[:15]
    json.dump(fewshot, open(os.path.join(REF, "rahul_fewshot.json"), "w"),
              indent=2, ensure_ascii=False)

    span = f"{last_n[-1]['createdAt']} -> {last_n[0]['createdAt']}" if last_n else "n/a"
    print(f"  corpus: {len(last_n)} posts ({span})")
    print(f"  few-shot: {len(fewshot)} high-engagement breakdown posts")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    main(n)
