"""
Second-pass geocoding for the stations the first pass missed or mismatched
(102 of 188). Two fixes over pass 1:
  1. Strip decorations that confuse the geocoder: trailing "(Club Med A)",
     trailing " A"/" B", trailing digits ("Batu Feringgi 3" -> "Batu Feringgi").
  2. Constrain the search to a bounding box around the station's OWN state
     (Nominatim `viewbox` + `bounded=1`) so "Pantai Damai" in Sarawak can no
     longer match a same-named beach in Kedah.

Anything still unresolved after this keeps its pass-1 fallback (state
centroid + jitter) from fix_station_coords.py, run again afterwards.

Run: python dosm_dashboard/scripts/geocode_retry.py
"""
import csv
import json
import os
import re
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROC = os.path.join(ROOT, "data", "processed")
COORDS_CSV = os.path.join(PROC, "mmwqi_station_coords.csv")
GEOJSON = os.path.join(PROC, "malaysia_states.geojson")

HEADERS = {"User-Agent": "dosm-datathon-dashboard/1.0 (student project, contact: n/a)"}

STATE_FULL = {
    "Johor": "Johor", "Kedah": "Kedah", "Kelantan": "Kelantan", "Melaka": "Melaka",
    "N. Sembilan": "Negeri Sembilan", "P. Pinang": "Penang", "Pahang": "Pahang",
    "Perak": "Perak", "Sabah": "Sabah", "Sarawak": "Sarawak", "Selangor": "Selangor",
    "Terengganu": "Terengganu", "W.P. Labuan": "Labuan",
}
CANON = {
    "Johor": "Johor", "Kedah": "Kedah", "Kelantan": "Kelantan", "Melaka": "Malacca",
    "N. Sembilan": "Negeri Sembilan", "P. Pinang": "Penang", "Pahang": "Pahang",
    "Perak": "Perak", "Sabah": "Sabah", "Sarawak": "Sarawak", "Selangor": "Selangor",
    "Terengganu": "Terengganu", "W.P. Labuan": "Labuan",
}


def clean_name(name):
    n = re.sub(r"\([^)]*\)", "", name)          # drop "(Club Med A)"
    n = re.sub(r"\s+[A-Z]$", "", n)              # drop trailing " A"
    n = re.sub(r"\s*\d+$", "", n)                # drop trailing " 3" or "3"
    return n.strip(" -")


def state_bbox(canon_name):
    with open(GEOJSON, encoding="utf-8") as f:
        gj = json.load(f)
    for feat in gj["features"]:
        if feat["properties"]["canonical_state"] == canon_name:
            from shapely.geometry import shape
            b = shape(feat["geometry"]).bounds  # (minx, miny, maxx, maxy) = (lon,lat,lon,lat)
            return b
    return None


def geocode(query, viewbox=None):
    params = {"q": query, "format": "json", "limit": 1, "countrycodes": "my"}
    if viewbox:
        minx, miny, maxx, maxy = viewbox
        params["viewbox"] = f"{minx},{maxy},{maxx},{miny}"  # left,top,right,bottom
        params["bounded"] = 1
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    if data:
        return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("display_name", "")
    return None, None, ""


def state_ok(state_raw, match_text):
    expect = STATE_FULL.get(state_raw, state_raw).lower()
    expect_alt = "melaka" if expect == "melaka" else expect
    return expect in match_text.lower() or expect_alt in match_text.lower()


def main():
    with open(COORDS_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    bbox_cache = {}
    n_fixed = 0
    for i, r in enumerate(rows):
        already_ok = r.get("lat") not in (None, "", "None") and state_ok(r["state"], r.get("match", ""))
        if already_ok:
            continue

        canon = CANON.get(r["state"], r["state"])
        if canon not in bbox_cache:
            bbox_cache[canon] = state_bbox(canon)
        bbox = bbox_cache[canon]
        state_full = STATE_FULL.get(r["state"], r["state"])

        cleaned = clean_name(r["area"])
        attempts = [
            (cleaned, bbox), (r["area"], bbox),
            (f"{cleaned}, {state_full}, Malaysia", bbox),
        ]
        found = False
        for q, vb in attempts:
            try:
                lat, lon, match = geocode(q, vb)
            except Exception as e:
                lat, lon, match = None, None, f"ERROR: {e}"
            time.sleep(1.1)
            if lat is not None and state_ok(r["state"], match):
                r["lat"], r["lon"], r["match"], r["query_used"] = lat, lon, match, q
                found = True
                n_fixed += 1
                break

        print(f"[{i+1}/{len(rows)}] {r['station']} {r['area']!r} "
              f"-> {'FIXED: ' + r['match'][:60] if found else 'still unresolved'}")

    fieldnames = ["station", "state", "area", "lat", "lon", "match", "query_used"]
    with open(COORDS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"\nFixed {n_fixed} additional stations with a scoped retry. -> {COORDS_CSV}")


if __name__ == "__main__":
    main()
