"""
Validate the Nominatim geocoding pass and patch it up:
- if a station has no lat/lon, OR the returned address doesn't mention the
  station's own state (a common failure mode for generic beach names that
  exist in several states, e.g. two different "Pantai Pasir Panjang"),
  fall back to that state's representative point with a small deterministic
  jitter so markers don't all stack exactly on one pixel.

Adds a `precision` column: "geocoded" (trust the point) vs "state_approx"
(state-level placeholder) so the app/report can be honest about it.

Run: python dosm_dashboard/scripts/fix_station_coords.py
"""
import hashlib
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROC = os.path.join(ROOT, "data", "processed")

STATE_FULL = {
    "Johor": "Johor", "Kedah": "Kedah", "Kelantan": "Kelantan", "Melaka": "Malacca",
    "N. Sembilan": "Negeri Sembilan", "P. Pinang": "Penang", "Pahang": "Pahang",
    "Perak": "Perak", "Sabah": "Sabah", "Sarawak": "Sarawak", "Selangor": "Selangor",
    "Terengganu": "Terengganu", "W.P. Labuan": "Labuan",
}
# Nominatim spells Malacca "Melaka" in addresses, unlike our canonical "Malacca"
STATE_MATCH_TEXT = {**STATE_FULL, "Melaka": "Melaka"}
STATE_MATCH_TEXT["Melaka"] = "Melaka"


def jitter(seed_text, scale=0.06):
    h = hashlib.md5(seed_text.encode()).hexdigest()
    dx = (int(h[:8], 16) / 0xFFFFFFFF - 0.5) * 2 * scale
    dy = (int(h[8:16], 16) / 0xFFFFFFFF - 0.5) * 2 * scale
    return dx, dy


def main():
    coords = pd.read_csv(os.path.join(PROC, "mmwqi_station_coords.csv"))
    centroids = pd.read_csv(os.path.join(PROC, "state_centroids.csv")).set_index("canonical_state")

    def state_ok(row):
        if pd.isna(row["lat"]):
            return False
        expect = str(STATE_FULL.get(row["state"], row["state"])).lower()
        # "Melaka" appears in Nominatim's own address text even though our
        # canonical name is "Malacca"; check both spellings.
        expect_alt = "melaka" if expect == "malacca" else expect
        text = str(row["match"]).lower()
        return expect in text or expect_alt in text

    coords["precision"] = coords.apply(lambda r: "geocoded" if state_ok(r) else "state_approx", axis=1)

    for idx, row in coords[coords.precision == "state_approx"].iterrows():
        canon = STATE_FULL.get(row["state"], row["state"])
        if canon not in centroids.index:
            continue
        base_lat, base_lon = centroids.loc[canon, ["lat", "lon"]]
        dx, dy = jitter(row["station"])
        coords.loc[idx, "lat"] = base_lat + dy
        coords.loc[idx, "lon"] = base_lon + dx

    out_path = os.path.join(PROC, "mmwqi_station_coords_fixed.csv")
    coords.to_csv(out_path, index=False)
    n_geo = (coords.precision == "geocoded").sum()
    n_approx = (coords.precision == "state_approx").sum()
    print(f"geocoded (trusted): {n_geo}   state-level fallback: {n_approx}   -> {out_path}")


if __name__ == "__main__":
    main()
