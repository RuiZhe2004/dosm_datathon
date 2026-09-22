"""
Systematic audit of all 188 MMWQI station coordinates:
1. Every point must fall inside its own state's polygon (tight buffer -
   coastal monitoring points sit right on the coastline, but a 0.2deg
   buffer used earlier is loose enough to hide a real error).
2. Distance-from-siblings check: within the same state, a station whose
   nearest neighbour is implausibly far away (>150km) is flagged for
   manual review - catches "right state, wrong end of it" errors that a
   polygon-containment check alone can't see.
3. Penang-specific island/mainland split check, since that's the failure
   mode already found once: cross-reference each Penang station's area
   name against known island vs mainland keywords and its actual longitude.
"""
import json
import os

import numpy as np
import pandas as pd
from shapely.geometry import shape, Point

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROC = os.path.join(ROOT, "data", "processed")

CANON = {
    "Johor": "Johor", "Kedah": "Kedah", "Kelantan": "Kelantan", "Melaka": "Malacca",
    "N. Sembilan": "Negeri Sembilan", "P. Pinang": "Penang", "Pahang": "Pahang",
    "Perak": "Perak", "Sabah": "Sabah", "Sarawak": "Sarawak", "Selangor": "Selangor",
    "Terengganu": "Terengganu", "W.P. Labuan": "Labuan",
}

ISLAND_KEYWORDS = ["batu feringgi", "ferringhi", "ferringgi", "tanjung bungah", "tanjong bungah",
                   "gurney", "batu maung", "bayan lepas", "george town", "jelutong",
                   "gertak sanggul", "teluk bahang", "miami", "pasir panjang"]
MAINLAND_KEYWORDS = ["perai", "butterworth", "bagan", "seberang"]
PENANG_ISLAND_LON_MAX = 100.36  # rough: island is west of this, mainland east


def main():
    with open(os.path.join(PROC, "malaysia_states.geojson"), encoding="utf-8") as f:
        gj = json.load(f)
    polys = {f["properties"]["canonical_state"]: shape(f["geometry"]) for f in gj["features"]}

    coords = pd.read_csv(os.path.join(PROC, "mmwqi_station_coords_fixed.csv"))
    coords["canon"] = coords["state"].map(lambda s: CANON.get(s, s))

    print("=" * 70)
    print("CHECK 1: strict polygon containment (0.05 deg buffer)")
    print("=" * 70)
    n_bad = 0
    for _, r in coords.iterrows():
        poly = polys.get(r["canon"])
        if poly is None or pd.isna(r["lat"]):
            continue
        pt = Point(r["lon"], r["lat"])
        if not poly.buffer(0.05).contains(pt):
            n_bad += 1
            print(f"  OUTSIDE STATE: {r['station']} ({r['canon']}) area={r['area']!r} "
                  f"lat={r['lat']:.4f} lon={r['lon']:.4f} precision={r['precision']}")
    print(f"-> {n_bad} station(s) outside their state polygon.\n")

    print("=" * 70)
    print("CHECK 2: within-state outlier distance (nearest sibling > 150km)")
    print("=" * 70)
    n_outlier = 0
    for state, grp in coords.dropna(subset=["lat", "lon"]).groupby("canon"):
        if len(grp) < 2:
            continue
        latlon = grp[["lat", "lon"]].to_numpy()
        for i, (idx, row) in enumerate(grp.iterrows()):
            d = np.sqrt(((latlon - latlon[i]) ** 2).sum(axis=1)) * 111  # rough km/deg
            d[i] = np.inf
            nearest = d.min()
            if nearest > 150:
                n_outlier += 1
                print(f"  ISOLATED: {row['station']} ({state}) area={row['area']!r} "
                      f"lat={row['lat']:.4f} lon={row['lon']:.4f} nearest_sibling_km={nearest:.0f} "
                      f"precision={row['precision']}")
    print(f"-> {n_outlier} isolated station(s) (may be legitimately remote, e.g. offshore islands).\n")

    print("=" * 70)
    print("CHECK 3: Penang island vs mainland name/coordinate consistency")
    print("=" * 70)
    pen = coords[coords.canon == "Penang"].copy()
    n_pen_bad = 0
    for _, r in pen.iterrows():
        name = str(r["area"]).lower()
        is_island_name = any(k in name for k in ISLAND_KEYWORDS)
        is_mainland_name = any(k in name for k in MAINLAND_KEYWORDS)
        is_island_coord = r["lon"] < PENANG_ISLAND_LON_MAX
        if is_island_name and not is_island_coord:
            n_pen_bad += 1
            print(f"  MISMATCH (name says island, coord says mainland): {r['station']} "
                  f"{r['area']!r} lon={r['lon']:.4f}")
        if is_mainland_name and is_island_coord:
            n_pen_bad += 1
            print(f"  MISMATCH (name says mainland, coord says island): {r['station']} "
                  f"{r['area']!r} lon={r['lon']:.4f}")
    print(f"-> {n_pen_bad} Penang island/mainland mismatch(es) out of {len(pen)} Penang stations.\n")

    print("=" * 70)
    print(f"Precision breakdown: {coords['precision'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
