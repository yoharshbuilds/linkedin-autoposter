"""OpenRouter client for text + image generation (one key for both)."""
import os
import base64
import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_HEADERS_EXTRA = {
    "HTTP-Referer": "https://github.com/linkedin-autoposter",
    "X-Title": "linkedin-autoposter",
}


def _key() -> str:
    k = os.environ.get("OPENROUTER_API_KEY")
    if not k:
        raise RuntimeError("OPENROUTER_API_KEY not set (put it in .env)")
    return k


def _headers() -> dict:
    return {"Authorization": f"Bearer {_key()}", "Content-Type": "application/json", **_HEADERS_EXTRA}


def chat(model: str, messages: list, temperature: float = 0.7, timeout: int = 120) -> str:
    """Return the assistant text for a chat completion."""
    body = {"model": model, "messages": messages, "temperature": temperature}
    r = requests.post(OPENROUTER_URL, headers=_headers(), json=body, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"OpenRouter text error: {data['error']}")
    return data["choices"][0]["message"]["content"]


def image(model: str, prompt: str, out_path: str, timeout: int = 180) -> str:
    """Generate an image and write it to out_path. Returns out_path."""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
    }
    r = requests.post(OPENROUTER_URL, headers=_headers(), json=body, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"OpenRouter image error: {data['error']}")
    msg = data["choices"][0]["message"]
    imgs = msg.get("images") or []
    if not imgs:
        raise RuntimeError(f"No image returned. Model said: {str(msg.get('content'))[:200]}")
    url = imgs[0]["image_url"]["url"]
    b64 = url.split(",", 1)[1]
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(b64))
    return out_path
