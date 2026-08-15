#!/usr/bin/env python3
"""Audit WordPress posts and identify likely duplicates.

The script is read-only with respect to WordPress. It writes JSON and Markdown
reports into the repository so that duplicate cleanup can be reviewed before
any destructive operation.
"""

from __future__ import annotations

import html
import json
import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from requests.auth import HTTPBasicAuth

TIMEOUT = 30
REPORT_JSON = Path("reports/wordpress-content-audit.json")
REPORT_MD = Path("reports/wordpress-content-audit.md")


class AuditError(RuntimeError):
    pass


def env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise AuditError(f"Missing required environment variable: {name}")
    return value


def api_url(site_url: str, endpoint: str) -> str:
    return urljoin(site_url.rstrip("/") + "/", f"wp-json/wp/v2/{endpoint.lstrip('/')}")


def request(session: requests.Session, url: str, **kwargs: Any) -> tuple[Any, requests.Response]:
    response = session.get(url, timeout=TIMEOUT, **kwargs)
    if not response.ok:
        try:
            details = response.json()
        except ValueError:
            details = response.text[:1000]
        raise AuditError(f"WordPress API {response.status_code} for {url}: {details}")
    return response.json(), response


def fetch_all(session: requests.Session, site_url: str, endpoint: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    page = 1
    items: list[dict[str, Any]] = []
    while True:
        current = dict(params)
        current.update({"page": page, "per_page": 100})
        batch, response = request(session, api_url(site_url, endpoint), params=current)
        items.extend(batch)
        total_pages = int(response.headers.get("X-WP-TotalPages", "1"))
        if page >= total_pages:
            return items
        page += 1


def strip_html(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", html.unescape(value))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def slug_family(slug: str) -> str:
    return re.sub(r"-\d+$", "", slug.strip().casefold())


def content_fingerprint(text: str) -> str:
    return normalize_text(text)[:500]


def embedded_author(post: dict[str, Any]) -> dict[str, Any]:
    embedded = post.get("_embedded", {})
    authors = embedded.get("author", []) if isinstance(embedded, dict) else []
    if authors and isinstance(authors[0], dict):
        return authors[0]
    return {}


def main() -> int:
    site_url = env("WP_SITE_URL")
    username = env("WP_USERNAME")
    password = env("WP_APPLICATION_PASSWORD").replace(" ", "")

    session = requests.Session()
    session.auth = HTTPBasicAuth(username, password)
    session.headers.update({"User-Agent": "civic-forensics-wordpress-audit/1.2"})

    me, _ = request(session, api_url(site_url, "users/me"), params={"context": "edit"})
    posts = fetch_all(
        session,
        site_url,
        "posts",
        {
            "status": "any",
            "context": "edit",
            "orderby": "date",
            "order": "desc",
            "_embed": "author",
        },
    )
    categories = fetch_all(session, site_url, "categories", {"context": "edit", "hide_empty": False, "_fields": "id,name,slug,count"})
    tags = fetch_all(session, site_url, "tags", {"context": "edit", "hide_empty": False, "_fields": "id,name,slug,count"})

    category_map = {int(item["id"]): item for item in categories}
    tag_map = {int(item["id"]): item for item in tags}

    records: list[dict[str, Any]] = []
    for post in posts:
        title = strip_html(post.get("title", {}).get("rendered", ""))
        content = strip_html(post.get("content", {}).get("rendered", ""))
        author = embedded_author(post)
        author_name = author.get("slug") or author.get("name") or f"user-{post.get('author', 0)}"
        record = {
            "id": int(post["id"]),
            "title": title,
            "normalized_title": normalize_text(title),
            "slug": post.get("slug", ""),
            "slug_family": slug_family(post.get("slug", "")),
            "status": post.get("status", ""),
            "date": post.get("date", ""),
            "modified": post.get("modified", ""),
            "link": post.get("link", ""),
            "author_id": int(post.get("author", 0)),
            "author": author_name,
            "category_ids": [int(value) for value in post.get("categories", [])],
            "categories": [category_map.get(int(value), {}).get("name", str(value)) for value in post.get("categories", [])],
            "tag_ids": [int(value) for value in post.get("tags", [])],
            "tags": [tag_map.get(int(value), {}).get("name", str(value)) for value in post.get("tags", [])],
            "word_count": len(content.split()),
            "content_fingerprint": content_fingerprint(content),
            "excerpt": strip_html(post.get("excerpt", {}).get("rendered", "")),
        }
        records.append(record)

    groups: dict[str, set[int]] = defaultdict(set)
    for record in records:
        if record["normalized_title"]:
            groups[f"title:{record['normalized_title']}"] .add(record["id"])
        if record["slug_family"]:
            groups[f"slug:{record['slug_family']}"] .add(record["id"])
        if len(record["content_fingerprint"]) >= 120:
            groups[f"content:{record['content_fingerprint']}"] .add(record["id"])

    id_to_record = {record["id"]: record for record in records}
    duplicate_sets: list[dict[str, Any]] = []
    seen: set[tuple[int, ...]] = set()
    for reason, ids in groups.items():
        if len(ids) < 2:
            continue
        key = tuple(sorted(ids))
        if key in seen:
            continue
        seen.add(key)
        members = [id_to_record[item] for item in key]
        duplicate_sets.append({"reason": reason.split(":", 1)[0], "posts": members})

    duplicate_sets.sort(key=lambda item: (-len(item["posts"]), item["posts"][0]["title"]))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "site_url": site_url,
        "authenticated_as": {"id": me.get("id"), "name": me.get("name"), "slug": me.get("slug")},
        "summary": {
            "posts": len(records),
            "published": sum(record["status"] == "publish" for record in records),
            "drafts": sum(record["status"] == "draft" for record in records),
            "authors": sorted({record["author"] for record in records}),
            "duplicate_groups": len(duplicate_sets),
        },
        "categories": categories,
        "tags": tags,
        "posts": records,
        "duplicate_groups": duplicate_sets,
    }

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# WordPress Content Audit",
        "",
        f"Generated: `{report['generated_at']}`",
        f"Site: {site_url}",
        f"Authenticated as: `{report['authenticated_as'].get('slug')}`",
        "",
        "## Summary",
        "",
        f"- Posts: **{len(records)}**",
        f"- Published: **{report['summary']['published']}**",
        f"- Drafts: **{report['summary']['drafts']}**",
        f"- Authors found: {', '.join(report['summary']['authors']) or 'none'}",
        f"- Likely duplicate groups: **{len(duplicate_sets)}**",
        "",
        "## Likely duplicate groups",
        "",
    ]
    if not duplicate_sets:
        lines.append("No likely duplicate groups were detected.")
    else:
        for index, group in enumerate(duplicate_sets, start=1):
            lines.extend([f"### Group {index} — matched by {group['reason']}", ""])
            for post in group["posts"]:
                lines.append(
                    f"- ID `{post['id']}` — **{post['title']}** — slug `{post['slug']}` — "
                    f"author `{post['author']}` — {post['word_count']} words — {post['status']}"
                )
            lines.append("")

    lines.extend(["## All posts", ""])
    for post in records:
        lines.append(
            f"- ID `{post['id']}` — **{post['title']}** — slug `{post['slug']}` — "
            f"author `{post['author']}` — categories: {', '.join(post['categories']) or 'none'}"
        )

    REPORT_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_JSON} and {REPORT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
