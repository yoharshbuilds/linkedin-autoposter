"""Generate the post's stat-card image via OpenRouter (gpt-5-image-mini)."""
import os

import llm


def build_prompt(image_fields: dict, cfg: dict) -> str:
    headline = image_fields.get("headline", "")
    stat = image_fields.get("stat", "")
    subtext = image_fields.get("subtext", "")
    return (
        f"{cfg['image_style']}\n\n"
        f"Headline text: \"{headline}\"\n"
        f"Big highlighted number: \"{stat}\"\n"
        f"Subtext: \"{subtext}\"\n"
        "Render this exact text accurately and legibly. No extra text, no watermarks, no logos."
    )


def make_image(image_fields: dict, cfg: dict, out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    prompt = build_prompt(image_fields, cfg)
    return llm.image(cfg["image_model"], prompt, out_path)
