"""Build static, crawlable pages, sitemap and JSON health responses for GitHub Pages."""
from __future__ import annotations

import datetime
import html
import json
import os
import re
import shutil
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit
from xml.sax.saxutils import escape as xml_escape

DEFAULT_SITE_URL = "https://jamesthemonkey.id-card.me/"
SITE_NAME = "James the Monkey"
HOME_TITLE = "James the Monkey | A Daily Illustrated Story"
HOME_DESCRIPTION = ("James the Monkey is a daily illustrated story. Follow a curious monkey "
                    "named James on his journey, with a new chapter and picture every day.")


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def story_text(entry: dict) -> str:
    return entry.get("story", "").replace("\\n", "\n")


def excerpt(entry: dict, limit: int = 155) -> str:
    text = " ".join(story_text(entry).split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:.")
    return cut + "…"


def format_date(iso: str) -> str:
    try:
        d = datetime.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    return f"{d:%A}, {d:%B} {d.day}, {d.year}"


def json_ld(data: dict) -> str:
    # "<" is escaped so story text can never close the script element.
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return f'<script type="application/ld+json">{body}</script>\n'


def entry_markup(entry: dict, image: str) -> str:
    """Server-side twin of renderEntry() in app.js."""
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", story_text(entry)) if p.strip()]
    story = "".join(f"<p>{esc(p)}</p>" for p in paragraphs)
    date = entry.get("date", "")
    location = entry.get("location") or ""
    return (
        f'<article class="entry" data-day="{int(entry["day"])}">\n'
        f'        <p class="entry-date"><time datetime="{esc(date)}">{esc(format_date(date))}</time></p>\n'
        f'        <h1 class="entry-title">{esc(entry["title"])}</h1>\n'
        f'        <div class="entry-image-wrap">\n'
        f'          <img src="{esc(image)}" alt="{esc(entry["title"])}" />\n'
        f'        </div>\n'
        f'        <div class="entry-story">{story}</div>\n'
        f'        <p class="entry-location">{esc(location)}</p>\n'
        f'      </article>'
    )


def page_html(template: str, *, title: str, description: str, canonical: str, image: str = "",
              og_type: str = "website", head_extra: str = "", main: str | None = None,
              strip_reader: bool = False) -> str:
    text = re.sub(r"<title>.*?</title>", lambda _: f"<title>{esc(title)}</title>", template, flags=re.S)
    values = {"description": description, "og:title": title, "og:description": description,
              "og:image": image, "og:type": og_type, "twitter:title": title,
              "twitter:description": description, "twitter:image": image}
    for name, value in values.items():
        pattern = r'(<meta\s+(?:name|property)="' + re.escape(name) + r'"\s+content=")[^"]*(")'
        text = re.sub(pattern, lambda m: m[1] + esc(value) + m[2], text)
    extras = f'<meta property="og:url" content="{esc(canonical)}" id="meta-og-url" />\n'
    extras += f'<link rel="canonical" href="{esc(canonical)}" id="canonical-url" />\n'
    extras += head_extra
    text = text.replace('<meta charset="utf-8" />', '<meta charset="utf-8" />\n' + extras, 1)
    if main is not None:
        text = re.sub(r'(<main id="main"[^>]*>).*?(</main>)', lambda m: f"{m[1]}\n      {main}\n    {m[2]}",
                      text, count=1, flags=re.S)
    if strip_reader:
        text = re.sub(r'\s*<nav class="story-nav".*?</nav>', "", text, count=1, flags=re.S)
        text = re.sub(r'\s*<div class="share-link-wrap">.*?</div>', "", text, count=1, flags=re.S)
        text = re.sub(r'\s*<script src="app\.js"></script>', "", text, count=1)
    return text


def image_url(site_url: str, entry: dict) -> str:
    return urljoin(site_url, "days/" + quote(entry["image"], safe=""))


def entry_url(site_url: str, day: int) -> str:
    return urljoin(site_url, f"entries/day-{day}/")


def entry_html(template: str, entry: dict, site_url: str) -> str:
    day = int(entry["day"])
    canonical = entry_url(site_url, day)
    image = image_url(site_url, entry)
    headline = f"Day {day}: {entry['title']}"
    description = excerpt(entry)
    article = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": headline[:110],
        "description": description,
        "image": [image],
        "datePublished": entry.get("date", ""),
        "url": canonical,
        "mainEntityOfPage": canonical,
        "author": {"@type": "Organization", "name": SITE_NAME, "url": site_url},
        "publisher": {"@type": "Organization", "name": SITE_NAME, "url": site_url},
        "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": site_url},
    }
    head = f'<base href="../../" />\n<meta name="james-day" content="{day}" />\n' + json_ld(article)
    return page_html(template, title=f"{headline} | {SITE_NAME}", description=description,
                     canonical=canonical, image=image, og_type="article", head_extra=head,
                     main=entry_markup(entry, "days/" + quote(entry["image"], safe="")))


def home_html(template: str, latest: dict, site_url: str) -> str:
    website = {"@context": "https://schema.org", "@type": "WebSite", "name": SITE_NAME,
               "alternateName": "James", "url": site_url, "description": HOME_DESCRIPTION}
    return page_html(template, title=HOME_TITLE, description=HOME_DESCRIPTION, canonical=site_url,
                     image=image_url(site_url, latest), head_extra=json_ld(website),
                     main=entry_markup(latest, "days/" + quote(latest["image"], safe="")))


def archive_html(template: str, entries: list, site_url: str) -> str:
    rows = "\n".join(
        f'          <li><a href="entries/day-{int(e["day"])}/"><span class="archive-day">Day {int(e["day"])}</span>'
        f' <span class="archive-title">{esc(e["title"])}</span></a>'
        f' <time datetime="{esc(e.get("date", ""))}">{esc(format_date(e.get("date", "")))}</time></li>'
        for e in sorted(entries, key=lambda e: e["day"], reverse=True)
    )
    count = len(entries)
    description = (f"Every chapter of {SITE_NAME}, a daily illustrated story: "
                   f"{count} {'entry' if count == 1 else 'entries'} from Day 1 onward.")
    main = (
        '<section class="archive">\n'
        '        <h1 class="entry-title">Every entry</h1>\n'
        f'        <p class="archive-intro">{esc(HOME_DESCRIPTION)}</p>\n'
        f'        <ol class="archive-list" reversed>\n{rows}\n        </ol>\n'
        '      </section>'
    )
    latest = max(entries, key=lambda e: e["day"]) if entries else None
    return page_html(template, title=f"All Entries | {SITE_NAME}", description=description,
                     canonical=urljoin(site_url, "entries/"),
                     image=image_url(site_url, latest) if latest else "",
                     head_extra='<base href="../" />\n', main=main, strip_reader=True)


def sitemap_xml(entries: list, site_url: str) -> str:
    latest = max((e.get("date", "") for e in entries), default="")
    urls = [(site_url, latest), (urljoin(site_url, "entries/"), latest)]
    urls += [(entry_url(site_url, int(e["day"])), e.get("date", ""))
             for e in sorted(entries, key=lambda e: e["day"])]
    body = "".join(
        f"  <url><loc>{xml_escape(loc)}</loc>"
        + (f"<lastmod>{xml_escape(mod)}</lastmod>" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", mod or "") else "")
        + "</url>\n"
        for loc, mod in urls
    )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + body + "</urlset>\n")


def robots_txt(site_url: str) -> str:
    path = urlsplit(site_url).path
    return (f"User-agent: *\nAllow: /\nDisallow: {path}health\n\n"
            f"Sitemap: {urljoin(site_url, 'sitemap.xml')}\n")


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
        (target / "index.html").write_text(entry_html(template, entry, site_url), encoding="utf-8")
    if entries:
        latest = max(entries, key=lambda e: e["day"])
        (output / "index.html").write_text(home_html(template, latest, site_url), encoding="utf-8")
    (output / "entries").mkdir(exist_ok=True)
    (output / "entries" / "index.html").write_text(archive_html(template, entries, site_url), encoding="utf-8")
    (output / "sitemap.xml").write_text(sitemap_xml(entries, site_url), encoding="utf-8")
    (output / "robots.txt").write_text(robots_txt(site_url), encoding="utf-8")
    health_dir = output / "health"
    health_dir.mkdir(exist_ok=True)
    (health_dir / "index.html").write_text(payload, encoding="utf-8")
    (output / "health.json").write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    source = Path(__file__).resolve().parents[1]
    build_site(source, source / "_site")
