"""GSO's system constraints, from its home page (LandingPage.aspx).

GSO writes two tables into the page itself (no PageMethod; seen by the probe on 15 Nov 2026):

  <div id="ctl00_MainContent_div_existsyscons">  "Existing Constraints"
      <table class='table tbl-constrain'><thead><tr><th>Type</th><th>Constrained Cct</th><th>Voltage</th>...
  <div id="ctl00_MainContent_div_consoutage">    "Constraints Due to Outage (for the next 7 days)"
      <table class='table tbl-constrain'><thead><tr><th>Start</th><th>End</th><th>Type</th><th>Constrained Cct</th>...

GSO describes them on the page: "Existing Constraint is described by its type of constraints such as inter-area power
transfer limitation; circuits in the Grid being constrained; transmission assets' voltage and thermal limits impact
from which generation clusters; and some additional operational remarks if any." and "Constraints Due to Outage is
described in similar manner however additional information is included which is the outage duration period of the
transmission assets giving rise to the system constraints".

Each row is kept exactly as GSO shows it, under GSO's own column headings (never renamed or interpreted: lesson 9),
as a list with every change (store.keep_table): "constraints_existing" and "constraints_outage". A row is known by
its whole content, so when GSO edits a row the old one shows as no longer listed and the new one as added.
"""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser

from .base import AdapterSpec, ParsedPayload, SchemaError

TABLES = {  # name in the archive -> id of the element GSO writes the table into
    "existing": "ctl00_MainContent_div_existsyscons",
    "outage": "ctl00_MainContent_div_consoutage",
}
EMPTY_NOTE = "GSO lists no constraints in this table at the moment"


class _TableReader(HTMLParser):
    """Collects the header cells and body rows of the first table inside the element with id `target`."""

    def __init__(self, target: str):
        super().__init__(convert_charrefs=True)
        self.target = target
        self.found = False
        self.depth = 0  # element depth inside the target element (0 = outside)
        self.in_table = self.done = False
        self.headers: list[str] = []
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._head = False

    VOID = {"br", "img", "hr", "input", "meta", "link", "col", "wbr"}

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        if not self.depth:
            if dict(attrs).get("id") == self.target:
                self.found, self.depth = True, 1
            return
        if tag not in self.VOID:
            self.depth += 1
        if tag == "table":
            self.in_table = True
        elif self.in_table and tag == "tr":
            self._close_cell()
            self._close_row()
            self._row = []
        elif self.in_table and tag in ("td", "th"):
            self._close_cell()  # a cell GSO left open ends where the next one starts
            if self._row is None:
                self._row = []
            self._cell, self._head = [], tag == "th"
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def _close_cell(self):
        if self._cell is not None and self._row is not None:
            text = re.sub(r"\s+", " ", "".join(self._cell)).strip()
            (self.headers if self._head else self._row).append(text)
        self._cell = None

    def _close_row(self):
        if self._row:
            self.rows.append(self._row)
        self._row = None

    def handle_endtag(self, tag):
        if self.done or not self.depth:
            return
        if tag in ("td", "th"):
            self._close_cell()
        elif tag == "tr":
            self._close_cell()
            self._close_row()
        elif tag == "table":
            self._close_cell()
            self._close_row()
            self.in_table, self.done = False, True
        if tag not in self.VOID:
            self.depth -= 1

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def read_table(html: str, element_id: str) -> tuple[list[str], list[list[str]]] | None:
    """GSO's column headings and body rows of the table inside `element_id`; None when the element is missing."""
    reader = _TableReader(element_id)
    reader.feed(html)
    reader.close()
    if not reader.found:
        return None
    return reader.headers, reader.rows


def _rows(headers: list[str], body: list[list[str]], notes: list[str], name: str) -> list[dict]:
    out, seen = [], {}
    for index, cells in enumerate(body):
        if len(cells) != len(headers):
            # A single cell across the table is GSO's own "nothing to show" line, not a constraint.
            if len(cells) == 1:
                notes.append(f"{name}: {cells[0] or EMPTY_NOTE}")
            else:
                notes.append(f"{name} row {index + 1}: {len(cells)} cells for {len(headers)} columns, not kept")
            continue
        fields = dict(zip(headers, cells))
        digest = hashlib.sha1("\x1f".join(cells).encode("utf-8")).hexdigest()[:12]
        seen[digest] = seen.get(digest, 0) + 1
        rid = digest if seen[digest] == 1 else f"{digest}-{seen[digest]}"  # GSO can list the same row twice
        label = next((fields[h] for h in headers if "constrain" in h.lower() and fields[h]), None) or cells[0]
        out.append({"id": rid, "name": label, **fields})
    return out


def parse_constraints(spec: AdapterSpec, html: str, ctx: dict) -> ParsedPayload:
    out = ParsedPayload(tables={})
    signature = []
    for name, element_id in TABLES.items():
        table = read_table(html, element_id)
        if table is None:
            raise SchemaError(f"GSO's home page no longer has the element {element_id} ({name} constraints)")
        headers, body = table
        if not headers and body:
            raise SchemaError(f"{name} constraints: a table without column headings")
        signature.append(f"{name}[{'|'.join(headers)}]")
        out.tables[name] = _rows(headers, body, out.rejected, name)
        if not out.tables[name] and not any(n.startswith(f"{name}:") for n in out.rejected):
            out.rejected.append(f"{name}: {EMPTY_NOTE}")
    out.signature = "constraints:" + ";".join(signature)
    return out


CONSTRAINTS = AdapterSpec(
    key="constraints",
    name="System constraints (existing, and due to outages in the next 7 days)",
    category="constraints",
    page="LandingPage.aspx",
    method="",
    verification="verified",
    description="GSO's two constraint tables from its home page, every 30 minutes: Existing Constraints, and "
                "Constraints Due to Outage (for the next 7 days). Each row is kept as GSO shows it, under GSO's own "
                "column headings, with every change (added, no longer listed).",
    takes_date=False,
    min_interval_seconds=1800,
    html_transform=parse_constraints,
)
