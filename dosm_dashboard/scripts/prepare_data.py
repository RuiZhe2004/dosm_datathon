"""
One-off data prep: turn the two notebook outputs into clean, joinable CSVs
that the Streamlit app reads directly (no modelling happens in the app).

Run from anywhere: `python dosm_dashboard/scripts/prepare_data.py`
"""
import os
import json

import pandas as pd
from shapely.geometry import shape

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NB = os.path.join(ROOT, "notebooks")
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed")
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------------------
# Canonical state names = the GeoJSON's shapeName. Every other spelling used
# across the two DOSM/DOE workbooks is mapped onto this one vocabulary so the
# map, the tourism table and the MMWQI table can all be joined on one key.
# ---------------------------------------------------------------------------
STATE_ALIASES = {
    "Johor": "Johor",
    "Kedah": "Kedah",
    "Kelantan": "Kelantan",
    "Melaka": "Malacca",
    "Negeri Sembilan": "Negeri Sembilan",
    "N. Sembilan": "Negeri Sembilan",
    "Pahang": "Pahang",
    "Perak": "Perak",
    "Perlis": "Perlis",
    "Pulau Pinang": "Penang",
    "P. Pinang": "Penang",
    "Penang": "Penang",
    "Sabah": "Sabah",
    "Sarawak": "Sarawak",
    "Selangor": "Selangor",
    "Terengganu": "Terengganu",
    "W.P. Kuala Lumpur": "Kuala Lumpur",
    "Kuala Lumpur": "Kuala Lumpur",
    "W.P. Labuan": "Labuan",
    "Labuan": "Labuan",
    "W.P. Putrajaya": "Putrajaya",
    "Putrajaya": "Putrajaya",
}

STATE_ISO = {
    "Selangor": "MY-10", "Johor": "MY-01", "Kuala Lumpur": "MY-14",
    "Malacca": "MY-04", "Negeri Sembilan": "MY-05", "Sabah": "MY-12",
    "Sarawak": "MY-13", "Kelantan": "MY-03", "Putrajaya": "MY-16",
    "Terengganu": "MY-11", "Pahang": "MY-06", "Kedah": "MY-02",
    "Perlis": "MY-09", "Perak": "MY-08", "Penang": "MY-07", "Labuan": "MY-15",
}


def canon(name):
    name = str(name).strip()
    return STATE_ALIASES.get(name, name)


# ---------------------------------------------------------------------------
# 1. GeoJSON — tag every feature with the canonical name + ISO so Plotly can
#    join on `canonical_state` directly.
# ---------------------------------------------------------------------------
def prep_geojson():
    with open(os.path.join(RAW, "malaysia_states.geojson"), encoding="utf-8") as f:
        gj = json.load(f)
    for feat in gj["features"]:
        name = canon(feat["properties"]["shapeName"])
        feat["properties"]["canonical_state"] = name
        feat["properties"]["iso"] = STATE_ISO.get(name, "")
    out_path = os.path.join(OUT, "malaysia_states.geojson")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(gj, f)
    print(f"[geojson] {len(gj['features'])} states -> {out_path}")

    # A representative point per state (guaranteed inside the polygon, unlike
    # a plain centroid which can land outside a concave shape). Used for the
    # clickable marker layer, since Plotly/Streamlit selection events aren't
    # reliably wired up for choropleth trace clicks.
    rows = []
    for feat in gj["features"]:
        geom = shape(feat["geometry"])
        pt = geom.representative_point()
        rows.append({"canonical_state": feat["properties"]["canonical_state"], "lat": pt.y, "lon": pt.x})
    centroids = pd.DataFrame(rows)
    centroids.to_csv(os.path.join(OUT, "state_centroids.csv"), index=False)
    print(f"[geojson] centroids -> {os.path.join(OUT, 'state_centroids.csv')}")
    return gj


# ---------------------------------------------------------------------------
# 2. Domestic tourism — actual flows (2011-2025) + forecast flows (2026-2028)
#    into one long table: origin, destination, year, visitors, kind.
# ---------------------------------------------------------------------------
def prep_tourism():
    src = os.path.join(NB, "domestic_tourism_forecast_2026_2028.xlsx")

    actual = pd.read_excel(src, sheet_name="tidy_flows")[["origin", "destination", "year", "visitors"]]
    actual["kind"] = "actual"

    flow_fc = pd.read_excel(src, sheet_name="fc_ml_flow_level")  # ML-only, flow-level
    flow_fc["kind"] = "forecast_ml"

    ensemble = pd.read_excel(src, sheet_name="fc_ensemble")  # state totals, 3-method ensemble
    ensemble_long = ensemble.melt(id_vars="year", var_name="destination", value_name="visitors")
    ensemble_long["origin"] = "Malaysia"  # marks "all origins" aggregate
    ensemble_long["kind"] = "forecast_ensemble_total"

    flows = pd.concat([actual, flow_fc, ensemble_long[["origin", "destination", "year", "visitors", "kind"]]],
                       ignore_index=True)
    flows["origin_canon"] = flows["origin"].map(canon)
    flows["destination_canon"] = flows["destination"].map(canon)
    flows = flows[flows["destination"] != "Malaysia"].copy()

    out_path = os.path.join(OUT, "tourism_flows.csv")
    flows.to_csv(out_path, index=False)
    print(f"[tourism] {len(flows)} rows ({flows.kind.value_counts().to_dict()}) -> {out_path}")

    # convenience: national trend line (actual + ensemble forecast), for the
    # top-line KPI / line chart when no state is selected.
    national_actual = (actual.groupby("year")["visitors"].sum() / 2).reset_index()
    # /2 because summing both origin and destination legs double counts trips;
    # dividing by 2 gives total trip-legs on a comparable footing to state totals.
    national_actual["kind"] = "actual"
    national_fc = ensemble.set_index("year").sum(axis=1).reset_index()
    national_fc.columns = ["year", "visitors"]
    national_fc["kind"] = "forecast_ensemble_total"
    national = pd.concat([national_actual, national_fc], ignore_index=True)
    national.to_csv(os.path.join(OUT, "tourism_national.csv"), index=False)
    return flows


# ---------------------------------------------------------------------------
# 3. MMWQI — long format, actual (2021-2025) + forecast (2026), one row per
#    station-year, ready to melt straight into the map / line charts.
# ---------------------------------------------------------------------------
def prep_mmwqi():
    fc = pd.read_excel(os.path.join(NB, "mmwqi_forecast_2026.xlsx"), sheet_name="forecast_2026")

    year_cols = [c for c in fc.columns if c.startswith("mmwqi_")]
    long_actual = fc.melt(
        id_vars=["state", "area", "station"], value_vars=year_cols,
        var_name="year", value_name="mmwqi",
    )
    long_actual["year"] = long_actual["year"].str.replace("mmwqi_", "").astype(int)
    long_actual["kind"] = "actual"
    long_actual["lower_95"] = pd.NA
    long_actual["upper_95"] = pd.NA

    long_fc = fc[["state", "area", "station", "pred_2026", "lower_95", "upper_95"]].copy()
    long_fc = long_fc.rename(columns={"pred_2026": "mmwqi"})
    long_fc["year"] = 2026
    long_fc["kind"] = "forecast"

    long = pd.concat([long_actual, long_fc[["state", "area", "station", "year", "mmwqi", "kind",
                                            "lower_95", "upper_95"]]], ignore_index=True)

    def category(score):
        if pd.isna(score):
            return None
        if score >= 90:
            return "Excellent"
        if score >= 80:
            return "Good"
        if score >= 51:
            return "Moderate"
        return "Poor"

    long["category"] = long["mmwqi"].map(category)
    long["state_canon"] = long["state"].map(canon)

    out_path = os.path.join(OUT, "mmwqi_long.csv")
    long.to_csv(out_path, index=False)
    print(f"[mmwqi] {len(long)} rows, {long.station.nunique()} stations -> {out_path}")

    # also keep the flat forecast table (has category_change, lower/upper etc.)
    fc.to_csv(os.path.join(OUT, "mmwqi_forecast_wide.csv"), index=False)
    return long


if __name__ == "__main__":
    prep_geojson()
    prep_tourism()
    prep_mmwqi()
    print("Done.")
