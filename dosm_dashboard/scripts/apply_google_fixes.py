"""
Apply hand-verified Google Maps coordinates for the stations OSM/Nominatim
couldn't place correctly (see README: geocode_stations.py / geocode_retry.py
still missed ~88 of 188 stations, several onto the wrong side of a strait or
the wrong state entirely — e.g. "Batu Maung" landing on the Penang mainland
instead of the island).

Each fix is still validated against the station's own state polygon (+ a
buffer, since coastal stations sit right on the boundary) before being
trusted; a fix that lands outside gets logged and skipped rather than risk
swapping one wrong pin for another.

Input: ../../google_fixes.csv (station, lat, lon, note)
Run: python dosm_dashboard/scripts/apply_google_fixes.py
"""
import json
import os

import pandas as pd
from shapely.geometry import shape, Point

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROC = os.path.join(ROOT, "data", "processed")
FIXES_CSV = os.path.join(ROOT, "data", "raw", "google_maps_fixes.csv")

CANON = {
    "Johor": "Johor", "Kedah": "Kedah", "Kelantan": "Kelantan", "Melaka": "Malacca",
    "N. Sembilan": "Negeri Sembilan", "P. Pinang": "Penang", "Pahang": "Pahang",
    "Perak": "Perak", "Sabah": "Sabah", "Sarawak": "Sarawak", "Selangor": "Selangor",
    "Terengganu": "Terengganu", "W.P. Labuan": "Labuan",
}
BUFFER_DEG = 0.2  # ~20km: coastal monitoring points sit right on/near the boundary


def main():
    with open(os.path.join(PROC, "malaysia_states.geojson"), encoding="utf-8") as f:
        gj = json.load(f)
    polys = {
        f["properties"]["canonical_state"]: shape(f["geometry"]).buffer(BUFFER_DEG)
        for f in gj["features"]
    }

    coords = pd.read_csv(os.path.join(PROC, "mmwqi_station_coords_fixed.csv"))
    fixes = pd.read_csv(FIXES_CSV)

    coords = coords.set_index("station")
    n_ok, n_rejected = 0, []
    for _, r in fixes.iterrows():
        station = r["station"]
        if station not in coords.index:
            continue
        state_raw = coords.loc[station, "state"]
        canon = CANON.get(state_raw, state_raw)
        poly = polys.get(canon)
        pt = Point(r["lon"], r["lat"])
        if poly is not None and poly.contains(pt):
            coords.loc[station, "lat"] = r["lat"]
            coords.loc[station, "lon"] = r["lon"]
            coords.loc[station, "precision"] = "geocoded"
            coords.loc[station, "match"] = f"Google Maps: {r['note']}"
            n_ok += 1
        else:
            n_rejected.append((station, canon, r["lat"], r["lon"]))

    coords = coords.reset_index()
    coords.to_csv(os.path.join(PROC, "mmwqi_station_coords_fixed.csv"), index=False)

    print(f"Applied {n_ok} Google Maps fixes (validated inside their state boundary + {BUFFER_DEG}deg buffer).")
    if n_rejected:
        print(f"Rejected {len(n_rejected)} fix(es) that fell outside their state boundary:")
        for s, c, lat, lon in n_rejected:
            print(f"  {s} (expected {c}): {lat},{lon}")

    n_geo = (coords.precision == "geocoded").sum()
    n_approx = (coords.precision == "state_approx").sum()
    print(f"\nFinal tally: {n_geo}/{len(coords)} geocoded, {n_approx} state-level fallback.")


if __name__ == "__main__":
    main()
