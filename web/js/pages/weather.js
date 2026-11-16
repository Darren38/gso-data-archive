// Weather at the LSS solar farms: Open-Meteo's sunshine and cloud forecast for each region (gso_archive/weather.py),
// set beside what the farms produced (GSO's solar map, data/farms/<day>.json). Not GSO data, and labelled so.
import { getFarmDays, getFarmsDay, getPoints } from "../data.js";
import { COLORS, timeChart } from "../charts.js";
import { implausibleSolar } from "../analysis.js";
import { addDays, card, emptyState, errorState, esc, fmtDate, fmtDateTime, fmtEnergy, fmtNum, getParam, h, kpi, loading, mytDay, mytDayStart, renderTable, setParams } from "../ui.js";

const REGIONS = ["north", "central", "south", "east"];
const TITLE = { all: "All regions", north: "North", central: "Central", south: "South", east: "East" };
const RCOL = { north: "#3b82f6", central: "#f59e0b", south: "#10b981", east: "#a855f7" };
const HALF_HOUR = 30 * 60e3;
const CREDIT = '<a href="https://open-meteo.com/" target="_blank" rel="noopener">Weather data by Open-Meteo.com</a> (<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC BY 4.0</a>)';

/** Open-Meteo's sunshine at time T is the average over the hour before T: drawn and matched at the middle of that hour. */
const centred = (points) => points.map(([t, v]) => [Date.parse(t) - HALF_HOUR, v]);
const iso = (ms) => new Date(ms).toISOString();

/** Linear interpolation of [[ms, v]] (sorted) at ms; null outside or across a gap over 2 hours. */
function at(points, ms) {
  for (let i = 1; i < points.length; i += 1) {
    const [t0, a] = points[i - 1], [t1, b] = points[i];
    if (ms < t0) return null;
    if (ms <= t1) return a == null || b == null || t1 - t0 > 2 * 3600e3 ? null : a + ((b - a) * (ms - t0)) / (t1 - t0);
  }
  return null;
}

/** Pearson correlation of [[x, y], ...]; null when either side doesn't vary. */
function pearson(pairs) {
  const n = pairs.length, mx = pairs.reduce((a, [x]) => a + x, 0) / n, my = pairs.reduce((a, [, y]) => a + y, 0) / n;
  let sxy = 0, sxx = 0, syy = 0;
  for (const [x, y] of pairs) { sxy += (x - mx) * (y - my); sxx += (x - mx) ** 2; syy += (y - my) ** 2; }
  return sxx > 0 && syy > 0 ? sxy / Math.sqrt(sxx * syy) : null;
}

/** Sunshine over one MYT day in kWh/m² ("peak sun hours"), when the day's sunlit hours (07:00-19:00) are all there. */
function sunHours(raw, day) {
  const a = mytDayStart(day).getTime(), b = a + 864e5;
  const inDay = raw.filter(([t, v]) => { const ms = Date.parse(t); return ms > a && ms <= b && v != null; });
  const need = Array.from({ length: 12 }, (_, i) => a + (8 + i) * 3600e3); // hours ending 08:00 .. 19:00
  if (!need.every((ms) => inDay.some(([t]) => Date.parse(t) === ms))) return null;
  return inDay.reduce((s, [, v]) => s + v, 0) / 1000;
}

/** A region's LSS output at every moment of the farm files: the sum over its farms when 90% of them have a reading. */
function fleet(files, region) {
  const out = [];
  let cap = 0;
  for (const f of files) {
    const times = f.times.map((t) => Date.parse(t));
    const farms = f.farms.filter((x) => (region === "all" || x.region.toLowerCase() === region) && x.cap
      && !implausibleSolar(x.mw.map((v, j) => [times[j], v]), x.cap));
    cap = Math.max(cap, farms.reduce((s, x) => s + x.cap, 0));
    times.forEach((ms, j) => {
      const vals = farms.map((x) => x.mw[j]).filter((v) => v != null);
      out.push([ms, farms.length && vals.length >= 0.9 * farms.length ? vals.reduce((s, v) => s + v, 0) : null]);
    });
  }
  out.sort((a, b) => a[0] - b[0]);
  return { points: out, cap };
}

export async function render(main, { meta, isCurrent }) {
  const have = REGIONS.filter((r) => meta.series.some((s) => s.key === `weather.${r}_ghi` && s.count));
  main.appendChild(h(`<div class="notice">Sunshine and cloud forecasts from Open-Meteo, a free weather service, for the middle of each region's
    LSS solar farms. <b>This is not GSO data.</b> ${CREDIT}. The farms' output beside it is GSO's solar map, as collected by this archive.</div>`));
  if (!have.length) {
    main.appendChild(h(card({ title: "Weather at the LSS farms", body: emptyState("No weather forecasts archived yet",
      "The forecast is fetched every 3 hours with the GSO readings. It appears here after the next collection.", "☁") })));
    return;
  }
  const region = ["all", ...REGIONS].includes(getParam("wx")) ? getParam("wx") : "all";
  const today = mytDay(new Date()), from = addDays(today, -1);
  const start = mytDayStart(from), end = mytDayStart(addDays(today, 3));
  // The estimate learns from the last few days with farm readings (one day of GSO outage leaves it the others).
  const learnFrom = addDays(today, -3);
  const body = h(`<div class="grid">${loading(120)}${loading(360)}</div>`);
  main.appendChild(body);
  try {
    const measuredKeys = have.map((r) => (meta.series.some((x) => x.key === `irradiance.${r}_ghi` && x.count) ? `irradiance.${r}_ghi` : null));
    const [ghi, meas, cloud, days] = await Promise.all([
      Promise.all(have.map((r) => getPoints(`weather.${r}_ghi`, mytDayStart(learnFrom), end))),
      Promise.all(measuredKeys.map((k) => (k ? getPoints(k, mytDayStart(learnFrom), end).catch(() => null) : null))),
      Promise.all(have.map((r) => getPoints(`weather.${r}_cloud`, start, end))),
      getFarmDays().catch(() => []),
    ]);
    const learnDays = days.filter((d) => d >= learnFrom && d <= today);
    const learnFiles = (await Promise.all(learnDays.map((d) => getFarmsDay(d).catch(() => null)))).filter((f) => f?.times?.length);
    const files = learnFiles.filter((f) => f.date >= from); // drawn: yesterday and today
    if (!isCurrent()) return;
    const fetched = meta.series.find((s) => s.key === `weather.${have[0]}_ghi`);
    const issued = ghi[0].points.length ? ghi[0].points[ghi[0].points.length - 1][3] : null;
    body.innerHTML = "";

    // ---- Sunshine per region: today and tomorrow, and a rough LSS estimate from how the farms did against the sunshine.
    const tomorrow = addDays(today, 1);
    const measured = (i) => (meas[i]?.points || []).filter((p) => p[1] != null);
    const rows = have.map((r, i) => {
      // Learn from the measured (satellite) sunshine when there is enough of it; the forecast otherwise.
      const basis = measured(i).length >= 12 ? "measured" : "forecast";
      const f = fleet(learnFiles, r), sun = centred(basis === "measured" ? measured(i) : ghi[i].points);
      // Yield: the farms' share of capacity per kW/m² of sunshine, over the daylight moments with both (sunshine > 50 W/m²).
      let num = 0, den = 0;
      for (const [ms, mw] of f.points) {
        const g = at(sun, ms);
        if (mw == null || g == null || g < 50 || !f.cap) continue;
        num += mw / f.cap; den += g / 1000;
      }
      // A real farm fleet turns roughly 60-90% of the sunshine's share into output. Far outside that, the forecast
      // and the farms disagree (wrong place, cloud timing, GSO gaps): no estimate rather than a misleading one.
      const raw = den > 2 ? num / den : null;
      const ratio = raw != null && raw >= 0.2 && raw <= 1.3 ? raw : null;
      const sTomorrow = sunHours(ghi[i].points, tomorrow);
      const nowCloud = at(centred(cloud[i].points), Date.now());
      const t0 = mytDayStart(today).getTime();
      const todayMeasured = measured(i).filter(([t]) => Date.parse(t) > t0).reduce((a, [, v]) => a + v, 0) / 1000;
      return { r, basis, todayMeasured: measured(i).length ? todayMeasured : null, cap: f.cap, today: sunHours(ghi[i].points, today), tomorrow: sTomorrow, ratio, nowCloud,
        estimate: ratio != null && sTomorrow != null && f.cap ? ratio * sTomorrow * f.cap : null };
    });
    body.appendChild(h(`<div class="grid kpis">${rows.map((x) => kpi({ icon: "solar", label: `${TITLE[x.r]}: sunshine tomorrow`,
      value: x.tomorrow == null ? null : fmtNum(x.tomorrow, 1), unit: "kWh/m²",
      meta: `Today ${x.todayMeasured != null ? `${fmtNum(x.todayMeasured, 1)} kWh/m² measured so far` : `${x.today == null ? "—" : fmtNum(x.today, 1)} kWh/m² forecast`}${x.nowCloud == null ? "" : ` · cloud now ${fmtNum(x.nowCloud)}%`}` })).join("")}</div>`));

    const est = rows.filter((x) => x.estimate != null);
    const estCard = h(card({ title: "LSS Farms Tomorrow: a Rough Estimate", sub: '<span class="tag third_party_documented">estimate by this site</span>',
      desc: `Tomorrow's sunshine forecast × how much the farms produced per unit of sunshine over the last few days (measured by satellite where
        available) × their capacity.
        A rough guide made by this site, <b>not a GSO forecast</b>: clouds rarely arrive exactly as forecast.`,
      body: est.length ? '<div class="tbl"></div>' : emptyState("Not enough readings yet", "It needs solar map readings and sunshine forecasts from the same recent days, and a full day of tomorrow's sunshine forecast.", "◌") }));
    body.appendChild(estCard);
    if (est.length) {
      const total = est.reduce((s, x) => s + x.estimate, 0), cap = est.reduce((s, x) => s + x.cap, 0);
      estCard.querySelector(".tbl").innerHTML = `<div class="table-wrap"><table><thead><tr><th>Region</th><th class="num">LSS capacity</th>
        <th class="num">Sunshine tomorrow</th><th class="num">Output per kWh/m²</th><th class="num">Energy tomorrow (estimate)</th><th class="num">Capacity factor</th></tr></thead><tbody>
        ${est.map((x) => `<tr><td>${TITLE[x.r]}</td><td class="num">${fmtNum(x.cap)} MW</td><td class="num">${fmtNum(x.tomorrow, 1)} kWh/m²</td>
          <td class="num">${fmtNum(100 * x.ratio, 0)}% of capacity</td><td class="num">${fmtEnergy(x.estimate)}</td><td class="num">${fmtNum((100 * x.estimate) / (24 * x.cap), 1)}%</td></tr>`).join("")}
        ${est.length > 1 ? `<tr><td><b>${est.length === rows.length ? "All" : "These regions"}</b></td><td class="num"><b>${fmtNum(cap)} MW</b></td><td></td><td></td><td class="num"><b>${fmtEnergy(total)}</b></td><td class="num"><b>${fmtNum((100 * total) / (24 * cap), 1)}%</b></td></tr>` : ""}
        </tbody></table></div><p class="small muted">"Output per kWh/m²": the farms' output as a share of their capacity for each 1 kW/m² of sunshine
        (a farm at full output in 1,000 W/m² sunshine would be 100%), learnt from ${est.every((x) => x.basis === "measured") ? "measured (satellite)" : est.some((x) => x.basis === "measured") ? "measured (satellite) or forecast" : "forecast"} sunshine. Farms marked "GSO figures look wrong" on the Solar page are left out.${est.length < rows.length ? ` Not estimated: ${rows.filter((x) => x.estimate == null).map((x) => TITLE[x.r]).join(", ")} (not enough matching readings, or the farms and the sunshine forecast disagree too much to trust).` : ""}</p>`;
    }

    // ---- Forecast charts
    const now = { markNow: true };
    const anyMeasured = meas.some((m) => m?.points?.some((p) => p[1] != null));
    const c1 = h(card({ title: anyMeasured ? "Sunshine by Region: Measured and Forecast" : "Sunshine Forecast by Region", sub: '<span class="tag third_party_documented">Open-Meteo, not GSO</span>',
      desc: `Sunshine reaching the ground (global horizontal irradiance, W/m²) at the middle of each region's LSS farms, yesterday to the day after tomorrow.
        ${anyMeasured ? "Solid lines: measured by the Himawari-9 weather satellite (each hour's average, about an hour behind). Dashed: forecast. " : ""}Dotted line: now.`,
      when: issued ? `Forecast fetched ${esc(fmtDateTime(issued))} MYT` : "", body: '<div class="chart tall"></div>' }));
    body.appendChild(c1);
    timeChart(c1.querySelector(".chart"), { ...now, unit: "W/m²", yAxes: [{ name: "W/m²", min: 0 }],
      series: have.flatMap((r, i) => [
        ...(measured(i).length ? [{ name: `${TITLE[r]} (measured)`, color: RCOL[r], width: 2,
          points: centred(measured(i)).filter(([ms]) => ms >= start.getTime()).map(([ms, v]) => [iso(ms), v, "satellite"]) }] : []),
        { name: anyMeasured ? `${TITLE[r]} (forecast)` : TITLE[r], color: RCOL[r], dashed: anyMeasured, width: anyMeasured ? 1.2 : undefined,
          points: centred(ghi[i].points).filter(([ms]) => ms >= start.getTime()).map(([ms, v]) => [iso(ms), v, "forecast"]) }]) });
    const c2 = h(card({ title: "Cloud Cover Forecast by Region", sub: '<span class="tag third_party_documented">Open-Meteo, not GSO</span>',
      desc: "Share of the sky covered by cloud (%), at the same places. More cloud usually means less solar output.", body: '<div class="chart"></div>' }));
    body.appendChild(c2);
    timeChart(c2.querySelector(".chart"), { ...now, unit: "%", yAxes: [{ name: "%", min: 0, max: 100 }],
      series: have.map((r, i) => ({ name: TITLE[r], color: RCOL[r], points: cloud[i].points })) });

    // ---- The farms against the sunshine, per region
    const c3 = h(card({ title: "LSS Output and Sunshine", desc: `Yellow area: the LSS farms' output (MW, GSO's solar map). Lines: sunshine (W/m², right scale),
        ${anyMeasured ? "solid as measured by satellite, dashed as forecast" : "as forecast"}.
        When the two shapes part, clouds or the farms themselves made the difference.`,
      right: `<div class="seg" role="group" aria-label="Region">${["all", ...have].map((r) => `<button type="button" data-r="${r}" aria-pressed="${r === region}">${TITLE[r]}</button>`).join("")}</div>`,
      body: '<div class="chart tall"></div>' }));
    body.appendChild(c3);
    const drawRegion = (r) => {
      c3.querySelectorAll("[data-r]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.r === r)));
      setParams({ wx: r === "all" ? null : r });
      const el = c3.querySelector(".chart");
      const f = fleet(files, r);
      if (!f.points.some((p) => p[1] != null)) { el.outerHTML = emptyState("No solar map readings yesterday or today"); return; }
      // "All": the sunshine of each region weighted by its farms' capacity.
      const idx = r === "all" ? have.map((_, i) => i) : [have.indexOf(r)];
      const weights = idx.map((i) => fleet(files, have[i]).cap);
      const wsum = weights.reduce((s, w) => s + w, 0) || 1;
      const blend = (pick, q) => {
        const base = centred(pick(idx[0]));
        return base.map(([ms]) => {
          const vs = idx.map((i) => at(centred(pick(i)), ms));
          return [iso(ms), vs.some((v) => v == null) ? null : vs.reduce((s, v, k) => s + v * weights[k], 0) / wsum, q];
        }).filter(([t]) => Date.parse(t) >= start.getTime() && Date.parse(t) <= Date.now() + 864e5);
      };
      const sun = blend((i) => ghi[i].points, "forecast");
      const sunMeasured = idx.every((i) => measured(i).length) ? blend((i) => measured(i), "satellite") : [];
      timeChart(el, { markNow: true, yAxes: [{ name: "MW", min: 0 }, { name: "W/m²", min: 0 }],
        series: [
          { name: `LSS output (${fmtNum(f.cap)} MW of farms)`, color: COLORS.solar, area: true, areaOpacity: 0.3, unit: "MW",
            points: f.points.filter((p) => p[0] >= start.getTime()).map(([ms, v]) => [iso(ms), v, "ok"]) },
          ...(sunMeasured.length ? [{ name: "Sunshine (measured)", color: "#3b82f6", yAxisIndex: 1, unit: "W/m²", points: sunMeasured, width: 2 }] : []),
          { name: sunMeasured.length ? "Sunshine (forecast)" : "Sunshine", color: sunMeasured.length ? "#93c5fd" : "#3b82f6", dashed: !!sunMeasured.length,
            yAxisIndex: 1, unit: "W/m²", points: sun, width: sunMeasured.length ? 1.4 : 2 },
        ] });
    };
    c3.querySelectorAll("[data-r]").forEach((b) => b.addEventListener("click", () => drawRegion(b.dataset.r)));
    drawRegion(have.includes(region) || region === "all" ? region : "all");

    // ---- How closely the farms follow the measured sunshine: each hour's average LSS output against the satellite's
    // sunshine for the same hour, per region and day (daylight hours only).
    if (anyMeasured) {
      const rel = [];
      for (const day of [...new Set(learnFiles.map((f) => f.date))].sort().reverse()) {
        const dayFiles = learnFiles.filter((f) => f.date === day);
        have.forEach((r, i) => {
          const f = fleet(dayFiles, r);
          const hours = measured(i).map(([t, v]) => [Date.parse(t), v]).filter(([ms]) => ms > mytDayStart(day).getTime() && ms <= mytDayStart(day).getTime() + 864e5);
          const pairs = [];
          for (const [end, g] of hours) {
            const inHour = f.points.filter(([ms, mw]) => mw != null && ms > end - 3600e3 && ms <= end).map(([, mw]) => mw);
            if (g >= 20 && inHour.length >= 3) pairs.push([g, inHour.reduce((a, b) => a + b, 0) / inHour.length]);
          }
          if (pairs.length < 4 || !f.cap) return;
          const sun = pairs.reduce((a, [g]) => a + g, 0) / 1000, energy = pairs.reduce((a, [, mw]) => a + mw, 0);
          rel.push({ day, region: TITLE[r], hours: pairs.length, sun, energy, perSun: (100 * energy) / (f.cap * sun), r: pearson(pairs) });
        });
      }
      const c4 = h(card({ title: "How Closely the Farms Follow the Sunshine", sub: '<span class="tag third_party_documented">worked out by this site</span>',
        desc: `For each daylight hour, the LSS farms' average output (GSO's solar map) set against the sunshine the Himawari-9 satellite measured for that hour.
          "Match" near 1 means output rose and fell with the sunshine; lower means something else mattered (local clouds, curtailment, farm problems, or GSO gaps).`,
        body: rel.length ? '<div class="tbl"></div>' : emptyState("Not enough matching hours yet", "It needs solar map readings and measured sunshine for the same daylight hours.", "◌") }));
      body.appendChild(c4);
      if (rel.length) {
        renderTable(c4.querySelector(".tbl"), [
          { key: "day", label: "Day", fmt: (v) => esc(fmtDate(v)) }, { key: "region", label: "Region" },
          { key: "hours", label: "Daylight hours compared", num: true, fmt: (v) => fmtNum(v) },
          { key: "sun", label: "Sunshine (measured)", num: true, fmt: (v) => `${fmtNum(v, 1)} kWh/m²` },
          { key: "energy", label: "LSS energy (those hours)", num: true, fmt: (v) => fmtEnergy(v) },
          { key: "perSun", label: "Output per kWh/m²", num: true, fmt: (v) => `${fmtNum(v, 0)}% of capacity` },
          { key: "r", label: "Match", num: true, fmt: (v) => (v == null ? "—" : fmtNum(v, 2)) },
        ], rel, 12);
      }
    }
    body.appendChild(h(`<p class="small muted">${CREDIT}; measured sunshine from the Himawari-9 satellite (JMA/JAXA) through Open-Meteo, fetched every hour. Forecasts are fetched every 3 hours${fetched?.last ? `; the newest runs to ${esc(fmtDateTime(fetched.last))} MYT` : ""}.
      Every fetched forecast is kept, so the archive also shows how the forecast changed.</p>`));
  } catch (err) { body.innerHTML = errorState(err); }
}
