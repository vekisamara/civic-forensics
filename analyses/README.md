# Civic Forensics Analyses

This directory contains evidence-based analyses of public decisions, institutional conduct, official claims, administrative performance and public-interest risks.

The primary focus is the European Union, its institutions, Member States and accession countries. Selected cases from other parts of the world are included where they reveal internationally relevant patterns of public administration, transparency, accountability, access to information, digital governance, public spending or quantitative formalism.

## Directory structure

- [`published/`](published/) — canonical, publication-ready analytical sources. WordPress-specific mirrors are maintained separately in [`../blog/`](../blog/).
- [`_global/`](_global/README.md) — selected analyses from other jurisdictions with broader comparative or methodological value.
- [`_templates/`](_templates/README.md) — standard templates for new analyses, quantitative reviews and source registers.
- [`_assets/`](_assets/README.md) — public, redacted visual material used in published analyses.

Directories prefixed with an underscore contain supporting or working material. Nothing in `analyses/` is automatically synchronized with WordPress.

## Publication threshold

An item belongs in this directory only when it:

1. addresses a public-interest question;
2. can be examined using verifiable sources;
3. applies the Civic Forensics methodology rather than merely summarising news;
4. distinguishes established facts, interpretation, inference and unresolved questions;
5. states limitations and missing evidence;
6. avoids unsupported allegations of intent, guilt, corruption or discrimination;
7. has comparative, educational or practical value.

## Standard analysis package

Each published analysis should normally use its own folder:

```text
YYYY-short-case-title/
├── README.md
├── analysis.md
├── sources.md
├── data/
└── assets/
```

Empty `data/` or `assets/` folders should not be created until they are needed.

## File naming

Use lowercase English names with hyphens and no spaces:

```text
2026-european-ombudsman-case-analysis
2026-eu-rule-of-law-report
2026-public-procurement-indicators
```

## Methodological basis

Analyses should identify the methodology and version used. Unless a specific reason is stated, new work should follow:

- *Standard for the Analysis of Public Decisions and Institutional Conduct*, version 3.2, EU-adapted edition;
- *Method of Disciplined Administrative Pressure*, version 3.2, EU-adapted edition;
- the applicable Civic Forensics source-status and evidence-level rules;
- the quantitative module whenever a material number, percentage, trend, ranking, projection or causal claim is examined.

## Status labels

Use one of the following status values in the document metadata:

- `draft` — working material not ready for citation;
- `reviewed` — internally checked but still open to correction;
- `final` — publication-ready version;
- `updated` — a final analysis revised after new evidence;
- `archived` — retained for record but no longer current.

## Evidence and privacy

Do not upload unredacted personal data, confidential records, private correspondence, authentication tokens or source files whose publication is not authorised. Store only public or properly redacted evidence. Where source material cannot be published, describe it precisely and state the limitation.

## Licence

Unless an individual analysis states otherwise, original analytical text is published under the repository licence. Third-party documents, screenshots, images and datasets retain their original rights and must be attributed separately.
