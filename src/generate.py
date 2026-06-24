"""Turn a news item into a LinkedIn post in Rahul's style (returns dict)."""
import json
import os
import re

import llm

HERE = os.path.dirname(__file__)
STYLE_PATH = os.path.join(HERE, "..", "prompts", "rahul_style.md")

# anything dash-like that reads as an em/en dash -> safe punctuation
_DASH = re.compile(r"\s*[—–‒―]\s*")


def strip_em_dashes(text: str) -> str:
    """Replace em/en dashes with a comma+space (the no-em-dash hard rule)."""
    return _DASH.sub(", ", text)


def _scrub(obj):
    """Recursively strip em dashes from any strings in a nested dict/list."""
    if isinstance(obj, str):
        return strip_em_dashes(obj)
    if isinstance(obj, list):
        return [_scrub(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items()}
    return obj


def _load_fewshot(cfg: dict) -> str:
    path = os.path.join(HERE, "..", cfg["fewshot_file"])
    try:
        posts = json.load(open(path))
    except FileNotFoundError:
        return ""
    lines = []
    for p in posts[: cfg.get("fewshot_count", 5)]:
        lines.append("EXAMPLE POST:\n" + (p.get("text") or "").strip())
    return "\n\n".join(lines)


def generate(item: dict, cfg: dict, angle: str = "", template_hint: str = "", facts: str = "") -> dict:
    style = open(STYLE_PATH).read()
    fewshot = _load_fewshot(cfg)
    source_block = (
        f"SOURCE ITEM\n"
        f"Title: {item.get('title','')}\n"
        f"Details: {item.get('summary','')}\n"
        f"Link: {item.get('url','')}\n"
        f"From: {item.get('source','')}\n"
    )
    if facts:
        source_block += f"\n{facts}\n"
    hint = ""
    if angle:
        hint += f"\nANGLE TO TAKE (his instinct): {angle}\n"
    if template_hint:
        hint += f"SUGGESTED IMAGE TEMPLATE: {template_hint} (use it only if the numbers support it).\n"
    numbers_rule = (
        "Use the RESEARCH FACT SHEET numbers as the backbone of the post and the image. "
        "Build the math image (returns_table or calc_worksheet) from the COMPUTED metric and its inputs. "
        if facts else
        "Use only facts and numbers present in the source. "
    )
    user = (
        f"{fewshot}\n\n{source_block}{hint}\n"
        "Write ONE LinkedIn post about this source item, in the style and structure described. "
        f"{numbers_rule}"
        "Never invent a number that is not in the source or fact sheet. Return STRICT JSON per the "
        "output format. Remember: absolutely no em dashes."
    )
    raw = llm.chat(cfg["text_model"], [
        {"role": "system", "content": style},
        {"role": "user", "content": user},
    ], temperature=0.7)

    data = _parse_json(raw)
    # enforce the no-em-dash rule defensively across the whole payload
    data["post_text"] = strip_em_dashes(data.get("post_text", "")).strip()
    data["tweet_text"] = strip_em_dashes(data.get("tweet_text", "")).strip()
    data["image"] = _scrub(data.get("image", {}) or {})
    return data


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    # strip markdown fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?|\n?```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # last-ditch: grab the outermost {...}
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise
