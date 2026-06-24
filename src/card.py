"""Render an HTML template to a PNG via headless Chrome (his self-made-graphic look)."""
import os
import json
import subprocess

ROOT = os.path.join(os.path.dirname(__file__), "..")
TEMPLATES = os.path.join(ROOT, "templates")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# rough heights so the screenshot viewport fits the content (logical px, before 2x scale)
def _height(template: str, data: dict) -> int:
    rows = len(data.get("rows", []) or [])
    apps = len(data.get("apps", []) or [])
    bars = len(data.get("bars", []) or [])
    if template == "returns_table":
        return 250 + rows * 56 + 40 * len(data.get("footnotes", []) or [])
    if template == "app_showdown":
        return 150 + apps * 235
    if template == "bar_chart":
        return 560
    return 480


_WIDTH = {"returns_table": 920, "bar_chart": 1040, "app_showdown": 805, "thesis_card": 920}


def render(template: str, data: dict, out_path: str, width: int = 0) -> str:
    width = width or _WIDTH.get(template, 920)
    src = os.path.join(TEMPLATES, template + ".html")
    html = open(src).read()
    inject = "<script>window.DATA=" + json.dumps(data) + "</script>"
    html = html.replace("</head>", inject + "</head>", 1) if "</head>" in html else inject + html
    tmp = out_path + ".html"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(tmp, "w").write(html)
    height = _height(template, data)
    subprocess.run([
        CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--force-device-scale-factor=2", "--default-background-color=FFFFFFFF",
        f"--screenshot={out_path}", f"--window-size={width},{height}",
        "file://" + os.path.abspath(tmp),
    ], capture_output=True, timeout=60)
    os.remove(tmp)
    return out_path
