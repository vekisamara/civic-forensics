#!/usr/bin/env python3
"""Read-only audit for duplicate WordPress posts.

Uses the same WordPress REST API credentials as the blog sync workflow.
It never modifies WordPress content.
"""

from __future__ import annotations

import hashlib
import html
import os
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from itertools import combinations

import requests

SITE = os.environ["WP_SITE_URL"].rstrip("/")
USER = os.environ["WP_USERNAME"]
PASSWORD = os.environ["WP_APPLICATION_PASSWORD"]
API = f"{SITE}/wp-json/wp/v2/posts"
STATUSES = ("publish", "draft", "pending", "private", "future")


def strip_html(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def norm_title(value: str) -> str:
    value = strip_html(value)
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(ch for ch in value if ch.isalnum() or ch.isspace())
    return re.sub(r"\s+", " ", value).strip()


def norm_content(value: str) -> str:
    return strip_html(value).casefold()


def fetch_posts() -> list[dict]:
    session = requests.Session()
    session.auth = (USER, PASSWORD)
    posts: dict[int, dict] = {}

    for status in STATUSES:
        page = 1
        while True:
            response = session.get(
                API,
                params={
                    "context": "edit",
                    "status": status,
                    "per_page": 100,
                    "page": page,
                    "_fields": "id,date,modified,slug,status,link,title,content",
                },
                timeout=30,
            )
            if response.status_code == 400 and "rest_post_invalid_page_number" in response.text:
                break
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break
            for post in batch:
                posts[int(post["id"])] = post
            total_pages = int(response.headers.get("X-WP-TotalPages", "1"))
            if page >= total_pages:
                break
            page += 1

    return sorted(posts.values(), key=lambda p: int(p["id"]))


def main() -> int:
    posts = fetch_posts()
    print(f"WORDPRESS DUPLICATE AUDIT\nSite: {SITE}\nPosts inspected: {len(posts)}\n")

    by_title: dict[str, list[dict]] = {}
    by_slug: dict[str, list[dict]] = {}
    by_hash: dict[str, list[dict]] = {}

    for post in posts:
        title = post.get("title", {}).get("raw") or post.get("title", {}).get("rendered", "")
        content = post.get("content", {}).get("raw") or post.get("content", {}).get("rendered", "")
        nt = norm_title(title)
        nc = norm_content(content)
        post["_audit_title"] = strip_html(title)
        post["_norm_title"] = nt
        post["_content_hash"] = hashlib.sha256(nc.encode("utf-8")).hexdigest() if nc else ""
        if nt:
            by_title.setdefault(nt, []).append(post)
        if post.get("slug"):
            by_slug.setdefault(post["slug"], []).append(post)
        if post["_content_hash"]:
            by_hash.setdefault(post["_content_hash"], []).append(post)

    exact_titles = [items for items in by_title.values() if len(items) > 1]
    duplicate_slugs = [items for items in by_slug.values() if len(items) > 1]
    identical_content = [items for items in by_hash.values() if len(items) > 1]

    similar_pairs = []
    for a, b in combinations(posts, 2):
        ta, tb = a["_norm_title"], b["_norm_title"]
        if not ta or not tb or ta == tb:
            continue
        ratio = SequenceMatcher(None, ta, tb).ratio()
        if ratio >= 0.90:
            similar_pairs.append((ratio, a, b))
    similar_pairs.sort(key=lambda x: x[0], reverse=True)

    def show_group(label: str, groups: list[list[dict]]) -> None:
        print(f"## {label}: {len(groups)}")
        if not groups:
            print("None\n")
            return
        for idx, items in enumerate(groups, 1):
            print(f"Group {idx}:")
            for p in items:
                print(f"  ID {p['id']} | {p['status']} | {p['_audit_title']} | /{p['slug']}/")
        print()

    show_group("Exact duplicate normalized titles", exact_titles)
    show_group("Duplicate slugs", duplicate_slugs)
    show_group("Identical normalized content", identical_content)

    print(f"## Near-duplicate titles (similarity >= 0.90): {len(similar_pairs)}")
    if not similar_pairs:
        print("None")
    else:
        for ratio, a, b in similar_pairs:
            print(f"  {ratio:.3f} | ID {a['id']} '{a['_audit_title']}' | ID {b['id']} '{b['_audit_title']}'")
    print()

    print("## Inventory")
    for p in posts:
        print(f"ID {p['id']} | {p['status']} | {p['_audit_title']} | /{p['slug']}/")

    flagged = len(exact_titles) + len(duplicate_slugs) + len(identical_content) + len(similar_pairs)
    print(f"\nAUDIT_FLAG_COUNT={flagged}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Audit failed: {exc}", file=sys.stderr)
        raise
