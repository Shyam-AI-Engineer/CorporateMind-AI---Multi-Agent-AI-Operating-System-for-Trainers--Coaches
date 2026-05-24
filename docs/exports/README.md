# Exported PDF Artifacts

This directory contains **generated PDF exports** of the project's core documentation. These files are the **distribution and sharing layer** — the editable source of truth is always the markdown file.

Do **not** edit PDFs directly. Regenerate from source (instructions below).

---

## What's Here

| File | Source | Description |
|---|---|---|
| `prd.pdf` | `docs/PRD.md` | Full Product Requirements Document (v3.0, 34 sections + appendices) |
| `architecture.pdf` | `docs/architecture.md` | System architecture reference for engineers |
| `CLAUDE.pdf` | `CLAUDE.md` (project root) | Engineering operating manual for AI + human contributors |

---

## How to Regenerate

Requires Node.js. Uses `md-to-pdf` (installed as a dev dependency or via `npx`).

### All three at once
```bash
# From the project root
npx md-to-pdf docs/PRD.md          --pdf-options '{"format":"A4","margin":{"top":"20mm","bottom":"20mm","left":"18mm","right":"18mm"}}' && mv docs/PRD.pdf docs/exports/prd.pdf
npx md-to-pdf docs/architecture.md --pdf-options '{"format":"A4","margin":{"top":"20mm","bottom":"20mm","left":"18mm","right":"18mm"}}' && mv docs/architecture.pdf docs/exports/architecture.pdf
npx md-to-pdf CLAUDE.md            --pdf-options '{"format":"A4","margin":{"top":"20mm","bottom":"20mm","left":"18mm","right":"18mm"}}' && mv CLAUDE.pdf docs/exports/CLAUDE.pdf
```

### Individual file
```bash
npx md-to-pdf docs/PRD.md && mv docs/PRD.pdf docs/exports/prd.pdf
```

---

## When to Regenerate

Regenerate the relevant PDF whenever the source markdown changes:

| Change | Regenerate |
|---|---|
| `docs/PRD.md` edited | `prd.pdf` |
| `docs/architecture.md` edited | `architecture.pdf` |
| `CLAUDE.md` (root) edited | `CLAUDE.pdf` |

**Rule:** Include the regenerated PDF in the same PR as the markdown change.

---

## Versioning

PDFs are **committed to the repository** and tracked by git. This ensures:
- Reviewers can download and read them without a local toolchain.
- Investors and partners receive a stable URL to the latest version.
- Releases tag a consistent set of documents alongside the code.

The `docs/exports/tmp/` subdirectory is gitignored (used for intermediate conversion artifacts).

---

## Tooling Notes

- `md-to-pdf` uses headless Chromium. If it fails with a launch error, ensure Chromium is accessible in your environment.
- Tables, code blocks, and headings render with GitHub-style styling.
- A4 format, 18–20 mm margins — optimized for print + screen readability.

---

*Generated artifacts only. See [`docs/README.md`](../README.md) for the full documentation index.*
