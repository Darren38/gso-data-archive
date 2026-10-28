"""Usage: python scripts/cut_map_outline.py countries-10m.json web/vendor/peninsular-malaysia.geo.json

Cut Peninsular Malaysia and its neighbours out of Natural Earth 1:10m (world-atlas countries-10m.json) as GeoJSON."""
import json, sys
src, out = sys.argv[1], sys.argv[2]
topo = json.load(open(src))
sx, sy = topo["transform"]["scale"]; tx, ty = topo["transform"]["translate"]
arcs = []
for arc in topo["arcs"]:
    x = y = 0; pts = []
    for dx, dy in arc:
        x += dx; y += dy; pts.append((x * sx + tx, y * sy + ty))
    arcs.append(pts)
def ring(idxs):
    pts = []
    for i in idxs:
        a = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts.extend(a if not pts else a[1:])
    return pts
BOX = (98.0, 0.6, 105.6, 7.6)  # lon/lat view around Peninsular Malaysia
def hits(r):
    xs = [p[0] for p in r]; ys = [p[1] for p in r]
    return not (max(xs) < BOX[0] or min(xs) > BOX[2] or max(ys) < BOX[1] or min(ys) > BOX[3])
def tidy(r):
    out = []
    for x, y in r:
        p = [round(x, 3), round(y, 3)]
        if not out or out[-1] != p: out.append(p)
    return out
keep = {"458": "Malaysia", "764": "Thailand", "702": "Singapore", "360": "Indonesia"}
feats = []
for g in topo["objects"]["countries"]["geometries"]:
    if str(g.get("id")) not in keep: continue
    polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
    sel = []
    for poly in polys:
        rings = [ring(r) for r in poly]
        if hits(rings[0]): sel.append([tidy(r) for r in rings])
    if sel:
        feats.append({"type": "Feature", "properties": {"name": keep[str(g["id"])]}, "geometry": {"type": "MultiPolygon", "coordinates": sel}})
json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w"), separators=(",", ":"))
print([f["properties"]["name"] for f in feats], sum(len(r) for f in feats for p in f["geometry"]["coordinates"] for r in p), "points")
