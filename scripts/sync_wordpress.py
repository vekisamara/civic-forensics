#!/usr/bin/env python3
"""Synchronize Markdown blog posts with WordPress through the REST API."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import frontmatter
import markdown
import requests
from requests.auth import HTTPBasicAuth

TIMEOUT = 30
AUTHOR_USERNAME = "gradjanskaforenzika"
RESERVED_FILENAMES = {"readme.md"}


class WordPressError(RuntimeError):
    pass


def env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise WordPressError(f"Missing required environment variable: {name}")
    return value


def normalize_site_url(value: str) -> str:
    return value.rstrip("/") + "/"


def api_url(site_url: str, endpoint: str) -> str:
    return urljoin(site_url, f"wp-json/wp/v2/{endpoint.lstrip('/')}")


def request(session: requests.Session, method: str, url: str, **kwargs: Any) -> Any:
    response = session.request(method, url, timeout=TIMEOUT, **kwargs)
    if not response.ok:
        try:
            details = response.json()
        except ValueError:
            details = response.text[:1000]
        raise WordPressError(f"WordPress API {response.status_code} for {url}: {details}")
    if response.status_code == 204:
        return None
    return response.json()


def find_term(session: requests.Session, site_url: str, taxonomy: str, name: str) -> int | None:
    items = request(
        session,
        "GET",
        api_url(site_url, taxonomy),
        params={"search": name, "per_page": 100, "context": "edit"},
    )
    for item in items:
        if item.get("name", "").casefold() == name.casefold():
            return int(item["id"])
    return None


def ensure_term(session: requests.Session, site_url: str, taxonomy: str, name: str) -> int:
    existing = find_term(session, site_url, taxonomy, name)
    if existing is not None:
        return existing
    created = request(
        session,
        "POST",
        api_url(site_url, taxonomy),
        json={"name": name},
    )
    return int(created["id"])


def find_author_id(session: requests.Session, site_url: str, username: str) -> int:
    users = request(
        session,
        "GET",
        api_url(site_url, "users"),
        params={"slug": username, "per_page": 10, "context": "view"},
    )
    for user in users:
        if user.get("slug", "").casefold() == username.casefold():
            return int(user["id"])
    raise WordPressError(
        f"WordPress author '{username}' was not found or is not visible through the REST API"
    )


def list_value(metadata: dict[str, Any], key: str) -> list[str]:
    value = metadata.get(key, [])
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise WordPressError(f"Front matter field '{key}' must be a string or list")


def wp_status(value: Any) -> str:
    status = str(value or "draft").strip().lower()
    mapping = {
        "published": "publish",
        "publish": "publish",
        "draft": "draft",
        "private": "private",
        "pending": "pending",
    }
    if status not in mapping:
        raise WordPressError(f"Unsupported status '{status}'")
    return mapping[status]


def remove_duplicate_h1(body: str, title: str) -> str:
    lines = body.lstrip().splitlines()
    if lines and re.fullmatch(r"#\s+" + re.escape(title.strip()), lines[0].strip()):
        return "\n".join(lines[1:]).lstrip()
    return body


def render_markdown(body: str) -> str:
    return markdown.markdown(
        body,
        extensions=["extra", "sane_lists", "smarty"],
        output_format="html5",
    )


def plain_text_excerpt(body: str, limit: int = 280) -> str:
    text = re.sub(r"```.*?```", " ", body, flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[#>*_`~\-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    shortened = text[: limit + 1].rsplit(" ", 1)[0].rstrip(".,;: ")
    return shortened + "…"


def find_post_by_slug(session: requests.Session, site_url: str, slug: str) -> dict[str, Any] | None:
    posts = request(
        session,
        "GET",
        api_url(site_url, "posts"),
        params={"slug": slug, "status": "any", "context": "edit", "per_page": 10},
    )
    return posts[0] if posts else None


def sync_file(
    session: requests.Session,
    site_url: str,
    path: Path,
    author_id: int,
) -> None:
    document = frontmatter.load(path)
    metadata = dict(document.metadata)

    title = str(metadata.get("title", "")).strip()
    slug = str(metadata.get("slug", "")).strip()
    if not title or not slug:
        raise WordPressError(f"{path}: front matter must contain title and slug")

    body = remove_duplicate_h1(document.content, title)
    content = render_markdown(body)

    category_ids = [
        ensure_term(session, site_url, "categories", name)
        for name in list_value(metadata, "categories")
    ]
    tag_ids = [
        ensure_term(session, site_url, "tags", name)
        for name in list_value(metadata, "tags")
    ]

    excerpt = str(metadata.get("excerpt", "")).strip() or plain_text_excerpt(body)

    payload: dict[str, Any] = {
        "title": title,
        "slug": slug,
        "content": content,
        "excerpt": excerpt,
        "status": wp_status(metadata.get("status")),
        "categories": category_ids,
        "tags": tag_ids,
        "author": author_id,
    }

    existing = find_post_by_slug(session, site_url, slug)
    if existing:
        result = request(
            session,
            "POST",
            api_url(site_url, f"posts/{existing['id']}"),
            json=payload,
        )
        action = "updated"
    else:
        result = request(session, "POST", api_url(site_url, "posts"), json=payload)
        action = "created"

    print(
        f"{action}: {path} -> post {result['id']} ({result['status']}) "
        f"author={AUTHOR_USERNAME} {result.get('link', '')}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="Markdown files to synchronize")
    args = parser.parse_args()

    site_url = normalize_site_url(env("WP_SITE_URL"))
    username = env("WP_USERNAME")
    password = env("WP_APPLICATION_PASSWORD")

    session = requests.Session()
    session.auth = HTTPBasicAuth(username, password)
    session.headers.update({"User-Agent": "civic-forensics-wordpress-sync/1.0"})

    try:
        author_id = find_author_id(session, site_url, AUTHOR_USERNAME)
        for raw_path in args.paths:
            path = Path(raw_path)
            if path.name.casefold() in RESERVED_FILENAMES:
                print(f"skipped reserved file: {path}")
                continue
            sync_file(session, site_url, path, author_id)
    except (WordPressError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
