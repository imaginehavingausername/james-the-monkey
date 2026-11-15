"""Build static entry previews and JSON health responses for GitHub Pages."""

import html
import json
import os
import re
import shutil
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

DEFAULT_SITE_URL = "https://jamesthemonkey.id-card.me/"


def entry_html(template: str, entry: dict, site_url: str, nested: bool = False) -> str:
    day = int(entry["day"])
    title = f"Day {day}: {entry['title']} | James the Monkey"
    description = " ".join(entry.get("story", "").replace("\\n", " ").split())
    description = description[:150] + ("…" if len(description) > 150 else "")
    image = urljoin(site_url, "days/" + quote(entry["image"], safe=""))
    canonical = urljoin(site_url, f"entries/day-{day}/")
    text = re.sub(r"<title>.*?</title>", lambda _: f"<title>{html.escape(title)}</title>", template, flags=re.S)
    values = {"description": description, "og:title": title, "og:description": description,
              "og:image": image, "twitter:title": title, "twitter:description": description,
              "twitter:image": image}
    for name, value in values.items():
        pattern = r'(<meta\s+(?:name|property)="' + re.escape(name) + r'"\s+content=")[^"]*(")'
        text = re.sub(pattern, lambda m: m[1] + html.escape(value, quote=True) + m[2], text)
    extras = f'<meta property="og:url" content="{html.escape(canonical, quote=True)}" id="meta-og-url" />\n'
    extras += f'<link rel="canonical" href="{html.escape(canonical, quote=True)}" id="canonical-url" />\n'
    if nested:
        extras += f'<base href="../../" />\n<meta name="james-day" content="{day}" />\n'
    return text.replace('<meta charset="utf-8" />', '<meta charset="utf-8" />\n' + extras)


def build_site(source: Path, output: Path, site_url=None) -> None:
    index = json.loads((source / "days" / "index.json").read_text(encoding="utf-8"))
    if not isinstance(index, list):
        raise ValueError("days/index.json must contain an array")
    if site_url is None:
        cname = source / "CNAME"
        site_url = os.environ.get("SITE_URL") or ("https://" + cname.read_text().strip() if cname.exists() else DEFAULT_SITE_URL)
    site_url = site_url.rstrip("/") + "/"
    if urlsplit(site_url).scheme not in ("http", "https") or not urlsplit(site_url).netloc:
        raise ValueError("SITE_URL must be an absolute HTTP(S) URL")
    payload = json.dumps({"days": len(index), "status": "ok"}, separators=(",", ":")) + "\n"

    # Keep tools, hidden files and private state out of the public artifact.
    shutil.copytree(source, output, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".*", "_*", "scripts", "tests", "README.md", "health", "entries"))
    template = (source / "index.html").read_text(encoding="utf-8")
    entries = []
    for item in index:
        day = item["day"]
        if not isinstance(day, int) or isinstance(day, bool) or day < 1:
            raise ValueError("Archive day numbers must be positive integers")
        entry = json.loads((source / "days" / f"day{day}.json").read_text(encoding="utf-8"))
        if entry.get("day") != day:
            raise ValueError(f"Archive entry day{day}.json has the wrong day number")
        entries.append(entry)
        target = output / "entries" / f"day-{day}"
        target.mkdir(parents=True, exist_ok=True)
        (target / "index.html").write_text(entry_html(template, entry, site_url, nested=True), encoding="utf-8")
    if entries:
        latest = max(entries, key=lambda e: e["day"])
        (output / "index.html").write_text(entry_html(template, latest, site_url), encoding="utf-8")
    health_dir = output / "health"
    health_dir.mkdir(exist_ok=True)
    (health_dir / "index.html").write_text(payload, encoding="utf-8")
    (output / "health.json").write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    source = Path(__file__).resolve().parents[1]
    build_site(source, source / "_site")

