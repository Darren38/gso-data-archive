# GSO Data Archive

## 👉 [Open the website](https://darren38.github.io/gso-data-archive/)

> The link goes live after the one-time GitHub Pages setup described in
> [Version 1 → Publishing the website](Version%201/README.md#publishing-the-website)
> (merge to `main`, then **Settings → Pages → Source: GitHub Actions**). Until a database
> is connected, the site shows a **watermarked demonstration dataset**, not GSO readings.

---

An independent, permanent archive and analytics dashboard for public data from Malaysia's
[Grid System Operator (GSO)](https://www.gso.org.my/) (Peninsular Malaysia), with a
focus on **solar generation**. It collects automatically on a 5-minute schedule, keeps every
reading and every later revision, and shows the history as charts, tables and CSV/Excel downloads.

## Versions

Each substantial iteration gets its own folder. Earlier versions are never overwritten.

| Version | Status | Summary |
|---|---|---|
| [Version 1](Version%201/README.md) | Current | Collector framework, PostgreSQL/SQLite archive with revision history, solar-first dashboard, automatic scheduling (worker or GitHub Actions), backups, 80 automated tests |

## Repository layout

```
gso-data-archive/
├── README.md                 ← this file (website link + version index)
├── .github/workflows/        ← CI, scheduled collection, Pages publishing, backups
└── Version 1/                ← self-contained project (see its README)
```

GitHub only runs workflows from `.github/workflows/` at the repository root, so the
workflows live here and point into the active version folder.
