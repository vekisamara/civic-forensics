# International Repository Migration Record

**Status:** completed
**Migration boundary:** English and international material moved to `civic-forensics`; Serbian and Bosnia and Herzegovina-focused material retained in `gradjanska-forenzika`.

## Source repository

`vekisamara/gradjanska-forenzika`

## Target repository

`vekisamara/civic-forensics`

## Completed scope

1. ECW Publication Kit moved to `publications/eu-compliance-watch/publication-kit/`.
2. CFP Publication Kit moved to `publications/civic-forensics-portfolio/publication-kit/`; current CFP-001 v0.5 remains canonical.
3. English analyses and templates moved to `analyses/`; WordPress mirrors remain in `blog/`.
4. Full EU public-statement and quick-analysis prompt sources moved under `prompts/eu/`.
5. Civic Intelligence Dashboard vision moved to `research-concepts/`.
6. Existing programme, publication and WordPress infrastructure retained.
7. Source-to-target file hashes, JSON syntax and internal links validated before source cleanup.
8. Serbian prompt mirrors removed from this repository because their canonical sources remain in `gradjanska-forenzika/promptovi/`.

## Repository boundary

- `civic-forensics`: international English-language publications, programmes, methods and partnerships.
- `gradjanska-forenzika`: Serbian-language and Bosnia and Herzegovina-focused civic oversight, casework and citizen resources.

The source repository was cleaned only after copy and integrity validation completed.
