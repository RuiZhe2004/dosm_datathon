"""
One-off geocoding of the 188 MMWQI station areas using OpenStreetMap's public
Nominatim API (no key needed). Results are cached to CSV so this only ever
needs to run once. Respects Nominatim's 1 req/sec usage policy.

Run: python dosm_dashboard/scripts/geocode_stations.py
"""
import csv
import os
import time
import urllib.parse
import urllib.request
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATIONS_CSV = os.path.join(ROOT, "data", "processed", "mmwqi_forecast_wide.csv")
OUT_CSV = os.path.join(ROOT, "data", "processed", "mmwqi_station_coords.csv")

HEADERS = {"User-Agent": "dosm-datathon-dashboard/1.0 (student project, contact: n/a)"}

# a few state name fixes that help Nominatim disambiguate small local beaches
STATE_FULL = {
    "Johor": "Johor", "Kedah": "Kedah", "Kelantan": "Kelantan", "Melaka": "Melaka",
    "N. Sembilan": "Negeri Sembilan", "P. Pinang": "Penang", "Pahang": "Pahang",
    "Perak": "Perak", "Sabah": "Sabah", "Sarawak": "Sarawak", "Selangor": "Selangor",
    "Terengganu": "Terengganu", "W.P. Labuan": "Labuan",
}


def geocode(query):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": query, "format": "json", "limit": 1, "countrycodes": "my",
    })
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    if data:
        return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("display_name", "")
    return None, None, ""


def main():
    import csv as _csv
    with open(STATIONS_CSV, encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))

    done = {}
    if os.path.exists(OUT_CSV):
        with open(OUT_CSV, encoding="utf-8") as f:
            for r in _csv.DictReader(f):
                done[r["station"]] = r

    fieldnames = ["station", "state", "area", "lat", "lon", "match", "query_used"]
    out_rows = list(done.values())

    for i, r in enumerate(rows):
        station = r["station"]
        if station in done and done[station].get("lat"):
            continue
        state_full = STATE_FULL.get(r["state"], r["state"])
        area = r["area"]

        attempts = [
            f"{area}, {state_full}, Malaysia",
            f"{area}, {state_full}",
            f"{area}, Malaysia",
        ]
        lat = lon = None
        match = ""
        used = ""
        for q in attempts:
            try:
                lat, lon, match = geocode(q)
            except Exception as e:
                lat, lon, match = None, None, f"ERROR: {e}"
            used = q
            time.sleep(1.1)  # Nominatim usage policy: max 1 req/sec
            if lat is not None:
                break

        out_rows.append({
            "station": station, "state": r["state"], "area": area,
            "lat": lat, "lon": lon, "match": match, "query_used": used,
        })
        print(f"[{i+1}/{len(rows)}] {station} {area!r} -> {lat}, {lon}")

        # write incrementally so a crash never loses progress
        with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
            w = _csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(out_rows)

    n_ok = sum(1 for r in out_rows if r.get("lat") not in (None, "", "None"))
    print(f"\nDone. Geocoded {n_ok}/{len(out_rows)} stations. -> {OUT_CSV}")


if __name__ == "__main__":
    main()
