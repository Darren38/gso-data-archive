// Checks of the numbers the pages work out themselves (web/js/analysis.js and rollup in data.js), on small
// hand-made readings whose right answers are known. Run by tests/test_frontend.py; prints "ok" when all pass.
import assert from "node:assert/strict";

globalThis.window = {}; // data.js reads its settings from window
const A = await import("../../web/js/analysis.js");
const { rollup } = await import("../../web/js/data.js");

const iso = (s) => new Date(s).toISOString();
const every10 = (from, n, value) => Array.from({ length: n }, (_, i) =>
  [new Date(Date.parse(from) + i * 600e3).toISOString(), typeof value === "function" ? value(i) : value]);

// Forecast miss: night (both zero) is no test of a forecast and must not shrink the typical miss.
{
  const actual = [...every10("2026-10-28T00:00:00+08:00", 3, 0), ...every10("2026-10-28T12:00:00+08:00", 2, 1000)];
  const forecast = [...every10("2026-10-28T00:00:00+08:00", 3, 0), ...every10("2026-10-28T12:00:00+08:00", 2, 900)];
  const e = A.forecastError(actual, forecast);
  assert.equal(e.n, 2);
  assert.equal(e.mae, 100);
  assert.equal(e.bias, -100); // forecast minus actual: actual was above the forecast
  // A forecast of zero when there was sun (or the reverse) is a real miss and still counts.
  assert.equal(A.forecastError([[iso("2026-10-28T07:10:00+08:00"), 50]], [[iso("2026-10-28T07:10:00+08:00"), 0]]).n, 1);
  assert.equal(A.forecastError([[iso("2026-10-28T01:00:00+08:00"), 0]], [[iso("2026-10-28T01:00:00+08:00"), 0]]), null);
}

// Stacking: a moment where any source has no reading is a gap for every layer, never a zero.
{
  const t = (m) => iso(`2026-10-28T12:${m}:00+08:00`);
  const [coal, gas] = A.alignStack([[[t("00"), 10], [t("10"), 11]], [[t("00"), 5], [t("10"), null]]]);
  assert.deepEqual(coal.map((p) => p[1]), [10, null]);
  assert.deepEqual(gas.map((p) => p[1]), [5, null]);
}

// Sums keep a moment only when every part has a reading.
{
  const t = iso("2026-10-28T12:00:00+08:00"), u = iso("2026-10-28T12:10:00+08:00");
  assert.deepEqual(A.sumSeries([[[t, 1], [u, 2]], [[t, 3]]]).map((p) => p[1]), [4, null]);
}

// Daily energy: a steady 100 MW for two whole days is 2,400 MWh each, including the slice across midnight.
{
  const pts = every10("2026-10-26T00:00:00+08:00", 2 * 144 + 1, 100);
  const { rows } = A.dailyFromPoints(pts, 600, "2026-10-26", "2026-10-27");
  assert.equal(rows.length, 2);
  for (const r of rows) {
    assert.ok(Math.abs(r.energy_mwh - 2400) < 1e-6, `${r.date}: ${r.energy_mwh}`);
    assert.equal(r.completeness, 1);
  }
  // Peak and its time, and a day with no readings is empty (not zero).
  const { rows: r2 } = A.dailyFromPoints(every10("2026-10-26T00:00:00+08:00", 144, (i) => (i === 80 ? 500 : 100)), 600, "2026-10-26", "2026-10-27");
  assert.equal(r2[0].max, 500);
  assert.equal(r2[0].max_time, iso("2026-10-26T13:20:00+08:00"));
  assert.equal(r2[1].count, 0);
  assert.equal(r2[1].max, null);
  assert.equal(r2[1].energy_mwh, null);
}

// Ramps: MW per minute between neighbouring readings; a missing reading breaks the ramp.
{
  const pts = every10("2026-10-28T08:00:00+08:00", 4, (i) => [0, 100, null, 300][i]);
  assert.deepEqual(A.ramps(pts, 600).map((p) => p[1]), [10, null, null]);
}

// Weeks are ISO weeks, as in gso_archive.analytics.rollup.
{
  const row = (date, max) => ({ date, count: 1, completeness: 1, max, max_time: `${date}T05:00:00Z`, energy_mwh: 10 });
  const weeks = rollup([row("2026-01-01", 1), row("2026-10-29", 2), row("2027-01-01", 3), row("2027-01-04", 4)], "week");
  assert.deepEqual(weeks.map((w) => w.period), ["2026-W01", "2026-W44", "2026-W53", "2027-W01"]);
  const month = rollup([row("2026-10-01", 7), row("2026-10-31", 9), { date: "2026-10-15", count: 0, completeness: 0, max: null, energy_mwh: null }], "month");
  assert.equal(month.length, 1);
  assert.equal(month[0].max, 9);
  assert.equal(month[0].days_with_data, 2);
  assert.equal(month[0].energy_mwh, 20);
}

console.log("ok");
