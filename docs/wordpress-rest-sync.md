# WordPress REST API synchronization

This repository can automatically create or update WordPress posts from Markdown files in `blog/`.

## Publishing flow

1. Create or edit an article in `blog/*.md`.
2. Push the change to `main`.
3. GitHub Actions runs `.github/workflows/sync-wordpress.yml`.
4. `scripts/sync_wordpress.py` reads YAML front matter and Markdown.
5. WordPress finds an existing post by `slug`.
6. The post is created or updated, and categories and tags are synchronized.

The synchronization is one-way: **GitHub → WordPress**. It never deletes WordPress posts.

## WordPress site

Expected site URL:

```text
https://analyses.civicforensics.org
```

Expected REST API root:

```text
https://analyses.civicforensics.org/wp-json/
```

## WordPress automation user

Create a separate WordPress user, for example:

```text
github-publisher
```

Recommended role: **Editor**.

Create an Application Password from the user profile and name it, for example:

```text
GitHub civic-forensics
```

Do not use the user's normal WordPress password.

## GitHub Actions secrets

In `vekisamara/civic-forensics`, open:

**Settings → Secrets and variables → Actions → New repository secret**

Add:

| Secret | Value |
|---|---|
| `WP_SITE_URL` | `https://analyses.civicforensics.org` |
| `WP_USERNAME` | WordPress automation username |
| `WP_APPLICATION_PASSWORD` | WordPress Application Password |

Do not add quotation marks. Spaces in the Application Password are accepted; the script removes them.

## First test

Open:

**Actions → Sync blog to WordPress → Run workflow**

A manual run synchronizes all Markdown files in `blog/`. Later pushes synchronize only changed Markdown files.

A post with the same `slug` is updated rather than duplicated.

## Front matter

```yaml
---
title: "Article title"
slug: "article-title"
language: en
status: draft
excerpt: "Short article summary."
categories:
  - Civic Forensics
  - EU Compliance Watch
tags:
  - AI Act
  - public authorities
  - transparency
---
```

Supported statuses:

- `draft`
- `published` or `publish`
- `private`
- `pending`

The `date` field may remain in the Markdown metadata for editorial records, but it is not sent to WordPress. This prevents date-format errors and preserves the existing WordPress publication date during updates.

If `excerpt` is omitted, the script creates a plain-text excerpt of approximately 280 characters.

## Security

- Use HTTPS only.
- Store credentials only in GitHub Actions Secrets.
- Use a dedicated WordPress account with the minimum necessary permissions.
- Revoke the Application Password if it is no longer needed or may have been exposed.
- Treat GitHub as the primary source: manual WordPress edits may be overwritten by the next synchronization.
