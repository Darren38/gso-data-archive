<div align="center">

# ☀️ GSO Grid Archive

**A permanent record of Peninsular Malaysia's electricity grid, with solar power front and centre.**

*Collects the Grid System Operator's public data every few minutes, keeps every reading forever, and turns it into charts, tables and downloads that update themselves.*

[![Open the site](https://img.shields.io/badge/OPEN%20THE%20SITE-darren38.github.io-2ea44f?style=for-the-badge)](https://darren38.github.io/gso-data-archive/)

<a href="https://darren38.github.io/gso-data-archive/"><img src="Version%203/docs/screenshot.jpg" alt="The Solar page of GSO Grid Archive showing seven days of solar generation against system demand. The picture uses the site's watermarked demonstration data, not GSO readings. Click to open the site." width="820"></a>

</div>

The site goes live after the one-time setup in [Version 3 → Publishing the site](Version%203/README.md#publishing-the-site-one-time).
Until the first real GSO readings arrive it shows watermarked **demonstration data**.

## Versions

Each big update gets its own folder, and older versions are kept as they were.

| Version | What it is |
|---|---|
| [Version 3](Version%203/README.md) | **Current.** New readings about every 2–3 minutes, pages that refresh themselves every minute, your view kept in the address, and a round of bug fixes found by clicking through everything |
| [Version 2](Version%202/README.md) | Runs entirely on GitHub (Actions + Pages, no server or database service), daily backups to a GitHub Release, site check-up after every update, downloadable archive |
| [Version 1](Version%201/README.md) | First release: collector, archive with full revision history, solar-first dashboard, tests. Needed your own server or database to keep collecting |

What changed and when: [CHANGELOG.md](CHANGELOG.md).

## Licence

Code: [MIT](LICENSE). Data: Grid System Operator (GSO) / Tenaga Nasional Berhad. Independent project, not affiliated with GSO or TNB.
