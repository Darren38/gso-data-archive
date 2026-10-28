// Small colourful icons for the headline number cards, drawn for this site in the spirit of GSO's home page tiles.
// Each is a 48×48 SVG; colours follow the chart colours (GSO's palette).

const svg = (body) => `<svg viewBox="0 0 48 48" aria-hidden="true" focusable="false">${body}</svg>`;
const rays = (cx, cy, r1, r2, color, n = 8) => Array.from({ length: n }, (_, i) => {
  const a = (i * 2 * Math.PI) / n;
  return `<line x1="${(cx + r1 * Math.cos(a)).toFixed(1)}" y1="${(cy + r1 * Math.sin(a)).toFixed(1)}" x2="${(cx + r2 * Math.cos(a)).toFixed(1)}" y2="${(cy + r2 * Math.sin(a)).toFixed(1)}" stroke="${color}" stroke-width="3" stroke-linecap="round"/>`;
}).join("");

export const ICONS = {
  // Solar panel with the sun behind it
  solar: svg(`<circle cx="35" cy="12" r="6" fill="#FFC30F"/>${rays(35, 12, 9, 12, "#FFC30F")}
    <path d="M8 22h26l-5 16H3z" fill="#2c4a7a"/>
    <path d="M14.5 22l-3.3 16M21 22l-4 16M27.5 22l-4.7 16M5.5 30h26.7" stroke="#9db8e3" stroke-width="1.4"/>
    <path d="M15 38h6v5h-6z" fill="#7a8796"/><path d="M11 43h14" stroke="#7a8796" stroke-width="2.5" stroke-linecap="round"/>`),
  // Transmission tower with a lightning bolt
  demand: svg(`<path d="M24 4l-9 40M24 4l9 40M17 34h14M19 24h10M20.5 16h7M12 12h24M15 21h18" stroke="#7a8796" stroke-width="2.4" stroke-linecap="round" fill="none"/>
    <path d="M10 10l-3 5M38 10l3 5" stroke="#7a8796" stroke-width="2" stroke-linecap="round"/>
    <path d="M27 18l-7 12h5l-3 11 9-14h-5l3-9z" fill="#FFC30F" stroke="#e08a00" stroke-width="1"/>`),
  // Pie with a yellow solar slice
  share: svg(`<circle cx="24" cy="24" r="18" fill="#466799"/>
    <path d="M24 24V6a18 18 0 0 1 15.6 27z" fill="#FFC30F"/>`),
  // Battery with a bolt
  battery: svg(`<rect x="6" y="13" width="32" height="22" rx="4" fill="none" stroke="#00C853" stroke-width="3"/>
    <rect x="39" y="19" width="4" height="10" rx="1.5" fill="#00C853"/>
    <rect x="10" y="17" width="10" height="14" rx="1.5" fill="#00C853" opacity=".35"/>
    <path d="M24 15l-6 10h5l-2 9 7-11h-5l2-8z" fill="#FFC30F" stroke="#e08a00" stroke-width="1"/>`),
  // Sun peeking over a cloud, for the forecast
  forecast: svg(`<circle cx="18" cy="17" r="8" fill="#FFC30F"/>${rays(18, 17, 11, 14, "#FFC30F")}
    <path d="M15 38a7 7 0 0 1 1-14 10 10 0 0 1 19 2 6 6 0 0 1 2 12z" fill="#e6edf5" stroke="#9aa5b1" stroke-width="1.5"/>
    <path d="M14 44h24" stroke="#23AF4E" stroke-width="2.5" stroke-dasharray="4 3" stroke-linecap="round"/>`),
  // Light bulb, for the highest value
  peak: svg(`<path d="M24 5a13 13 0 0 0-8 23c2 2 3 4 3 7h10c0-3 1-5 3-7A13 13 0 0 0 24 5z" fill="#FFC30F" stroke="#e08a00" stroke-width="1.5"/>
    <path d="M26 12l-5 9h4l-2 7" stroke="#8a5a00" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M19 38h10M20 42h8" stroke="#7a8796" stroke-width="2.6" stroke-linecap="round"/>`),
  // Bars with a rising arrow, for energy
  energy: svg(`<path d="M5 42h38" stroke="#7a8796" stroke-width="2.5" stroke-linecap="round"/>
    <rect x="8" y="30" width="6" height="11" fill="#f2ad00"/><rect x="17" y="24" width="6" height="17" fill="#f2ad00"/>
    <rect x="26" y="27" width="6" height="14" fill="#f2ad00"/><rect x="35" y="18" width="6" height="23" fill="#f2ad00"/>
    <path d="M6 22l10-8 8 5 15-12" stroke="#23AF4E" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M33 6h7v7" stroke="#23AF4E" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`),
  // Line climbing steeply, for the fastest rise
  rise: svg(`<path d="M6 40h36M6 40V8" stroke="#7a8796" stroke-width="2.5" stroke-linecap="round"/>
    <path d="M10 36l8-4 6-12 6-4 8-8" stroke="#f2ad00" stroke-width="3.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M31 8h7v7" stroke="#f2ad00" stroke-width="3.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`),
  // Arrow down, for the lowest value
  low: svg(`<circle cx="24" cy="24" r="18" fill="#466799" opacity=".15"/>
    <path d="M24 10v26M14 27l10 10 10-10" stroke="#466799" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`),
  // Clock, for "data updated"
  clock: svg(`<circle cx="24" cy="24" r="17" fill="none" stroke="#23AF4E" stroke-width="3"/>
    <path d="M24 13v11l7 5" stroke="#23AF4E" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M37 6l4 4M11 6l-4 4" stroke="#23AF4E" stroke-width="3" stroke-linecap="round"/>`),
  // Checklist, for readings collected
  check: svg(`<rect x="9" y="6" width="30" height="36" rx="3" fill="none" stroke="#7a8796" stroke-width="2.5"/>
    <path d="M14 16l3 3 5-6M14 28l3 3 5-6" stroke="#23AF4E" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M26 17h8M26 29h8" stroke="#7a8796" stroke-width="2.5" stroke-linecap="round"/>`),
  // Two arrows swapping, for the links to Thailand and Singapore
  exchange: svg(`<path d="M8 17h28M30 10l7 7-7 7" stroke="#2e8b57" stroke-width="3.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M40 31H12M18 24l-7 7 7 7" stroke="#3d6fb6" stroke-width="3.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`),
  // Plant ready to run, for availability
  plant: svg(`<path d="M5 42V24l9-6v6l9-6v6l9-6v24z" fill="#7a8796"/><rect x="34" y="8" width="7" height="34" fill="#5d6876"/>
    <rect x="10" y="30" width="4" height="4" fill="#FFC30F"/><rect x="18" y="30" width="4" height="4" fill="#FFC30F"/><rect x="26" y="30" width="4" height="4" fill="#FFC30F"/>
    <path d="M4 42h40" stroke="#464646" stroke-width="2.5" stroke-linecap="round"/>`),
  // Fuels, for "biggest source now"
  coal: svg(`<path d="M5 42V26l9-6v6l9-6v6l9-6v22z" fill="#5c5c5c"/><rect x="34" y="12" width="7" height="30" fill="#474747"/>
    <path d="M37 9c-2-3 3-4 1-7M40 9c1-2 4-2 3-5" stroke="#9aa5b1" stroke-width="2" fill="none" stroke-linecap="round"/>
    <path d="M4 42h40" stroke="#2f2f2f" stroke-width="2.5" stroke-linecap="round"/>`),
  gas: svg(`<path d="M24 4c3 9 13 13 13 25a13 13 0 0 1-26 0c0-6 3-10 6-13 0 5 2 7 4 8-1-8 1-14 3-20z" fill="#428DF5"/>
    <path d="M24 26c2 4 6 6 6 11a6 6 0 0 1-12 0c0-3 2-5 3-6 0 2 1 3 2 3 0-3 0-5 1-8z" fill="#bcd6fb"/>`),
  hydro: svg(`<path d="M24 4C18 14 10 22 10 31a14 14 0 0 0 28 0c0-9-8-17-14-27z" fill="#25D366"/>
    <path d="M17 31a7 7 0 0 0 7 7" stroke="#e8fbef" stroke-width="3" fill="none" stroke-linecap="round"/>`),
  oil: svg(`<rect x="12" y="8" width="24" height="34" rx="3" fill="#FC5E55"/><path d="M12 18h24M12 32h24" stroke="#c0392b" stroke-width="2.5"/>`),
};

/** Icon for a fuel series key, e.g. "generation_mix.gas". */
export function fuelIcon(key = "") {
  const k = key.split(".")[1] || "";
  if (k.includes("solar")) return "solar";
  return ["coal", "gas", "hydro", "oil"].includes(k) ? k : "plant";
}
