// Runtime configuration. `gso-archive export-static` overwrites this file with mode "static".
// mode "api":    the dashboard calls the read-only API at apiBase (same origin when empty).
// mode "static": the dashboard reads pre-exported JSON files under dataBase (GitHub Pages).
window.GSO_CONFIG = window.GSO_CONFIG || { mode: "api", apiBase: "", dataBase: "data" };
