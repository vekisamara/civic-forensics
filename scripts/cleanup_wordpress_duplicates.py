#!/usr/bin/env python3
"""Consolidate duplicate WordPress posts identified by the audit report.

For every connected duplicate component, the script keeps one canonical post,
merges taxonomy assignments, exports the canonical content to blog/<slug>.md,
and moves the remaining copies to WordPress Trash. Trash is recoverable.
"""

from __future__ import annotations

import html
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import frontmatter
import html2text
import requests
from requests.auth import HTTPBasicAuth

TIMEOUT = 30
REPORT = Path("reports/wordpress-content-audit.json")
LOG = Path("reports/wordpress-cleanup-result.md")
BLOG = Path("blog")


class CleanupError(RuntimeError):
    pass


def env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise CleanupError(f"Missing required environment variable: {name}")
    return value


def api_url(site_url: str, endpoint: str) -> str:
    return urljoin(site_url.rstrip("/") + "/", f"wp-json/wp/v2/{endpoint.lstrip('/')}")


def request(session: requests.Session, method: str, url: str, **kwargs: Any) -> Any:
    response = session.request(method, url, timeout=TIMEOUT, **kwargs)
    if not response.ok:
        try:
            details = response.json()
        except ValueError:
            details = response.text[:1000]
        raise CleanupError(f"WordPress API {response.status_code} for {url}: {details}")
    return response.json()


def union_find_components(groups: list[dict[str, Any]]) -> list[set[int]]:
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for group in groups:
        ids = [int(post["id"]) for post in group.get("posts", [])]
        if not ids:
            continue
        for post_id in ids[1:]:
            union(ids[0], post_id)

    components: dict[int, set[int]] = defaultdict(set)
    for post_id in parent:
        components[find(post_id)].add(post_id)
    return sorted(components.values(), key=lambda values: min(values))


def is_numbered_duplicate(slug: str) -> bool:
    return bool(re.search(r"-\d+$", slug))


def choose_canonical(records: list[dict[str, Any]]) -> dict[str, Any]:
    return min(
        records,
        key=lambda item: (
            is_numbered_duplicate(str(item.get("slug", ""))),
            str(item.get("date", "9999")),
            int(item["id"]),
        ),
    )


def rendered(field: Any) -> str:
    if isinstance(field, dict):
        return str(field.get("rendered", ""))
    return str(field or "")


def clean_title(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def html_to_markdown(value: str) -> str:
    converter = html2text.HTML2Text()
    converter.body_width = 0
    converter.ignore_images = False
    converter.ignore_links = False
    converter.unicode_snob = True
    return converter.handle(value).strip() + "\n"


def term_names(session: requests.Session, site_url: str, taxonomy: str, ids: list[int]) -> list[str]:
    names: list[str] = []
    for term_id in sorted(set(ids)):
        term = request(session, "GET", api_url(site_url, f"{taxonomy}/{term_id}"), params={"context": "edit"})
        names.append(str(term.get("name", term_id)))
    return names


def export_post(session: requests.Session, site_url: str, post: dict[str, Any]) -> Path:
    slug = str(post["slug"])
    title = clean_title(rendered(post.get("title")))
    body = html_to_markdown(rendered(post.get("content")))
    excerpt = clean_title(rendered(post.get("excerpt")))
    categories = term_names(session, site_url, "categories", [int(v) for v in post.get("categories", [])])
    tags = term_names(session, site_url, "tags", [int(v) for v in post.get("tags", [])])

    document = frontmatter.Post(body)
    document.metadata = {
        "title": title,
        "slug": slug,
        "status": "published" if post.get("status") == "publish" else post.get("status", "draft"),
        "language": "English",
        "author": "civicforensics",
        "categories": categories,
        "tags": tags,
        "excerpt": excerpt,
        "wordpress_post_id": int(post["id"]),
    }
    BLOG.mkdir(parents=True, exist_ok=True)
    path = BLOG / f"{slug}.md"
    path.write_text(frontmatter.dumps(document) + "\n", encoding="utf-8")
    return path


def main() -> int:
    if os.getenv("CONFIRM_CLEANUP", "").strip() != "TRASH_DUPLICATES":
        raise CleanupError("CONFIRM_CLEANUP must equal TRASH_DUPLICATES")
    if not REPORT.exists():
        raise CleanupError(f"Missing audit report: {REPORT}")

    audit = json.loads(REPORT.read_text(encoding="utf-8"))
    records = {int(item["id"]): item for item in audit.get("posts", [])}
    components = union_find_components(audit.get("duplicate_groups", []))

    site_url = env("WP_SITE_URL")
    username = env("WP_USERNAME")
    password = env("WP_APPLICATION_PASSWORD").replace(" ", "")
    session = requests.Session()
    session.auth = HTTPBasicAuth(username, password)
    session.headers.update({"User-Agent": "civic-forensics-wordpress-cleanup/1.0"})

    me = request(session, "GET", api_url(site_url, "users/me"), params={"context": "edit"})
    author_id = int(me["id"])

    lines = ["# WordPress Duplicate Cleanup", "", f"Authenticated as: `{me.get('slug')}`", ""]
    total_trashed = 0

    for index, component in enumerate(components, start=1):
        component_records = [records[post_id] for post_id in component if post_id in records]
        if len(component_records) < 2:
            continue
        canonical_record = choose_canonical(component_records)
        canonical_id = int(canonical_record["id"])
        category_ids = sorted({int(v) for item in component_records for v in item.get("category_ids", [])})
        tag_ids = sorted({int(v) for item in component_records for v in item.get("tag_ids", [])})

        canonical = request(session, "GET", api_url(site_url, f"posts/{canonical_id}"), params={"context": "edit"})
        canonical = request(
            session,
            "POST",
            api_url(site_url, f"posts/{canonical_id}"),
            json={
                "author": author_id,
                "categories": category_ids,
                "tags": tag_ids,
                "status": "publish",
            },
        )
        export_path = export_post(session, site_url, canonical)

        trashed: list[int] = []
        for post_id in sorted(component):
            if post_id == canonical_id:
                continue
            request(session, "DELETE", api_url(site_url, f"posts/{post_id}"), params={"force": "false"})
            trashed.append(post_id)
            total_trashed += 1

        lines.extend([
            f"## Group {index}",
            "",
            f"- Canonical post: `{canonical_id}` — **{clean_title(rendered(canonical.get('title')))}**",
            f"- Canonical slug: `{canonical.get('slug')}`",
            f"- Repository file: `{export_path}`",
            f"- Trashed duplicates: {', '.join(f'`{value}`' for value in trashed)}",
            "",
        ])

    lines.extend([f"Total duplicate posts moved to Trash: **{total_trashed}**", ""])
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("\n".join(lines), encoding="utf-8")
    print(f"Cleanup complete: {total_trashed} posts moved to Trash")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
