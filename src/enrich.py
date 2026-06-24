"""Research a story the way Rahul does BEFORE writing: go to primary sources, pull the
hard numbers, compute the derived metric (MOIC, multiples, unit economics), show the math.

Uses an OpenRouter web-enabled model (the ':online' suffix) so it can reach filings,
TRACXN, and company financials at run time. Strict rule: only real numbers it actually
finds. If a number is not found it is marked UNKNOWN and no metric is fabricated from it.
"""
import json
import os
import re

import requests

import llm

ROOT = os.path.join(os.path.dirname(__file__), "..")
METHOD = os.path.join(ROOT, "reference", "research_method.md")
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


def fetch_article(url: str, limit: int = 6000) -> str:
    """Pull the primary article body (best-effort) so research starts from the source text."""
    if not url or not url.startswith("http"):
        return ""
    try:
        html = requests.get(url, headers=_UA, timeout=20).text
    except Exception:
        return ""
    html = re.sub(r"(?is)<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>", " ", html)
    # prefer paragraph text
    paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", html)
    text = " ".join(re.sub(r"<[^>]+>", "", p) for p in paras)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 200:  # fallback: strip everything
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
    return text[:limit]


def research(item: dict, cfg: dict) -> dict:
    """Return a fact sheet of real numbers + computed metrics, or {} if research is off/fails."""
    if not cfg.get("enable_research", True):
        return {}
    model = cfg.get("research_model") or (cfg["text_model"] + ":online")
    method = open(METHOD).read()
    article = fetch_article(item.get("url", ""))

    prompt = (
        f"{method}\n\n"
        "STORY TO RESEARCH:\n"
        f"Headline: {item.get('title','')}\n"
        f"Source: {item.get('source','')}  URL: {item.get('url','')}\n"
        f"Coverage text:\n{article or item.get('summary','')}\n\n"
        "Do the research now. Use web search to reach the primary sources (RHP/DRHP, MCA/ROC, "
        "TRACXN, company filings, official releases). Pull the specific line items, then compute "
        "the metric Rahul would (MOIC, multiple, XIRR, implied unit economics) and SHOW the formula "
        "with its inputs. Use ONLY numbers you actually find. If a needed input is missing, set it to "
        "\"UNKNOWN\" and do not compute a metric that depends on it. Return STRICT JSON only:\n"
        "{\n"
        '  "facts": [{"point": "the fact with its number and period", "source": "filing/source name"}],\n'
        '  "computed": [{"metric": "MOIC", "value": "6.24x", "formula": "Rs 112.47 cr FMV / Rs 18.02 cr cost", "inputs_found": true}],\n'
        '  "nuance": "the angle/nuance the coverage missed (one line), or empty",\n'
        '  "sources": ["url1", "url2"],\n'
        '  "confidence": "high|medium|low"\n'
        "}"
    )
    try:
        raw = llm.chat(model, [
            {"role": "system", "content": "You are a meticulous venture/financial research analyst. "
             "You never invent numbers. Every figure traces to a real source."},
            {"role": "user", "content": prompt},
        ], temperature=0.2)
    except Exception as e:
        print(f"  [warn] research call failed: {e}")
        return {}

    data = _parse_json(raw)
    if not data:
        return {}
    # keep only computed metrics whose inputs were actually found
    data["computed"] = [c for c in data.get("computed", [])
                        if c.get("inputs_found") and "UNKNOWN" not in str(c.get("formula", ""))]
    return data


def factsheet_text(r: dict) -> str:
    """Render the research dict into a compact authoritative block for the writer."""
    if not r:
        return ""
    lines = ["RESEARCH FACT SHEET (verified numbers, use these. Do NOT invent beyond them):"]
    for f in r.get("facts", []):
        src = f" [{f['source']}]" if f.get("source") else ""
        lines.append(f"- {f.get('point','')}{src}")
    if r.get("computed"):
        lines.append("COMPUTED (show this math in the image if it fits):")
        for c in r["computed"]:
            lines.append(f"- {c.get('metric','')} = {c.get('value','')}  ({c.get('formula','')})")
    if r.get("nuance"):
        lines.append(f"NUANCE THE COVERAGE MISSED: {r['nuance']}")
    if r.get("confidence"):
        lines.append(f"(research confidence: {r['confidence']})")
    return "\n".join(lines)


def _parse_json(raw: str) -> dict:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?|\n?```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return {}
    return {}
