"""GSO's system constraints: the two tables GSO writes into its home page (seen by the probe on 15 Nov 2026).

The page below copies GSO's markup (element ids, table class, column headings as far as the probe showed them);
the cell values are made up for the test and are not GSO's."""

from datetime import date

import pytest

from gso_archive import analytics, store
from gso_archive.adapters import ADAPTERS, NOT_IMPLEMENTED, get_adapter, parse
from gso_archive.adapters.base import SchemaError
from gso_archive.collector import collect_one

DAY = date(2026, 11, 16)
# GSO's column headings as the trial read them from GSO's page (15 Nov 2026). Shortened tables keep the first ones.
HEAD_EXIST = "<thead><tr><th>Type</th><th>Constrained Cct</th><th class='text-center'>Voltage</th><th>Other</th></tr></thead>"
HEAD_OUT = "<thead><tr><th>Start</th><th>End</th><th>Type</th><th>Constrained Cct</th><th class='text-center'>Voltage</th></tr></thead>"


def page(existing_rows: str, outage_rows: str) -> str:
    return f"""<html><body><h2 class="title-line text-center">Existing Constraints</h2><p>...</p>
    <div id="ctl00_MainContent_div_existsyscons" class="col-md-12 no-padding"><table class='table tbl-constrain'>{HEAD_EXIST}<tbody>{existing_rows}</tbody></table></div>
    <h2 class="title-line text-center">Constraints Due to Outage (for the next 7 days)</h2>
    <div id="ctl00_MainContent_div_consoutage" class="col-md-12"><table class='table tbl-constrain'>{HEAD_OUT}<tbody>{outage_rows}</tbody></table></div>
    </body></html>"""


EXIST = "<tr><td>Test type A</td><td>Test circuit 1 &amp; 2</td><td class='text-center'>275kV</td><td>Test<br>remark</td></tr>"
OUT1 = "<tr><td>01/01/2099 08:00</td><td>02/01/2099 17:00</td><td>Test type B</td><td>Test circuit 3</td><td>132kV</td></tr>"
OUT2 = "<tr><td>03/01/2099 08:00</td><td>03/01/2099 17:00</td><td>Test type C</td><td>Test circuit 4</td><td>500kV</td></tr>"


def test_rows_are_kept_under_gsos_own_headings():
    p = parse(get_adapter("constraints"), page(EXIST, OUT1 + OUT2).encode(), DAY, {})
    ex, out = p.tables["existing"], p.tables["outage"]
    assert len(ex) == 1 and len(out) == 2 and not p.readings
    assert {k: v for k, v in ex[0].items() if k != "id"} == {
        "name": "Test circuit 1 & 2", "Type": "Test type A", "Constrained Cct": "Test circuit 1 & 2",
        "Voltage": "275kV", "Other": "Test remark"}
    assert list(out[0])[2:] == ["Start", "End", "Type", "Constrained Cct", "Voltage"]
    assert out[0]["Start"] == "01/01/2099 08:00" and out[0]["id"] != out[1]["id"]
    assert p.signature.startswith("constraints:existing[Type|Constrained Cct|Voltage|Other];outage[Start|End|")


def test_an_empty_list_or_gsos_no_data_line_keeps_no_rows():
    p = parse(get_adapter("constraints"), page("", "<tr><td colspan='5'>No Record Found</td></tr>").encode(), DAY, {})
    assert p.tables == {"existing": [], "outage": []}
    assert any("No Record Found" in n for n in p.rejected) and any(n.startswith("existing:") for n in p.rejected)


def test_cells_gso_leaves_open_are_still_read():
    p = parse(get_adapter("constraints"), page("<tr><td>A<td>B<td>C<td>D<tr><td>E<td>F<td>G<td>H", "").encode(), DAY, {})
    assert [r["Type"] for r in p.tables["existing"]] == ["A", "E"] and p.tables["existing"][1]["Other"] == "H"


def test_a_page_without_the_tables_is_a_changed_page():
    with pytest.raises(SchemaError):
        parse(get_adapter("constraints"), b"<html><body>GSO</body></html>", DAY, {})


def test_constraints_are_no_longer_a_missing_category():
    assert "constraints" in ADAPTERS and "constraints" not in NOT_IMPLEMENTED


def test_collection_keeps_both_lists_and_every_change(engine, client, fake, settings):
    spec = get_adapter("constraints")
    fake.add("GET LandingPage.aspx", page(EXIST, OUT1), page(EXIST, OUT2))
    assert collect_one(engine, client, settings, spec, DAY).status == "success"
    assert collect_one(engine, client, settings, spec, DAY).status == "success"
    assert [c.method for c in fake.calls].count("POST") == 0  # read from the page itself, no PageMethod
    with engine.connect() as conn:
        out = analytics.table(conn, "constraints_outage")
        ex = analytics.table(conn, "constraints_existing")
    assert [(r["Constrained Cct"], r["listed"]) for r in out["rows"]] == [("Test circuit 4", True), ("Test circuit 3", False)]
    assert sorted(c["change"] for c in out["changes"]) == ["added", "no longer listed"]
    assert len(ex["rows"]) == 1 and ex["changes"] == []  # the first list is the starting point, not additions
    with engine.connect() as conn:
        assert store.get_state(conn, "table:constraints_existing")["checked_at"]
