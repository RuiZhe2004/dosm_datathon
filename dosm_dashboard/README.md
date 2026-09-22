# Malaysia Domestic Tourism & Coastal Water Quality Dashboard

DOSM Datathon 2026. Streamlit app with three tabs:

1. **Domestic Tourism** — choropleth map of Malaysia by state, filterable by
   state of origin and year (2011–2025 actual, 2026–2028 model forecast),
   with top-destinations bar chart, share-of-destinations pie chart, and a
   state-of-origin → state-visited trend line with its forecast.
2. **Coastal Tourism Risk (CTRS)** — choropleth + ranking of the CTRS/TSRI
   composite risk score (tourism exposure + environmental stress − marine
   protection) across 13 states, a per-state X/Y/Z component breakdown, and
   an explainer + data-caveats panel. Reads the precomputed result straight
   from `TSRI_CTRS_model.xlsx`'s `CTRS_Summary` sheet — the app does not
   recompute the index.
3. **Coastal Water Quality (MMWQI)** — pin map of 188 DOE monitoring
   stations, colour-coded by water quality category, zooming to a state when
   picked; hovering a pin shows the current reading and the 2026 forecast
   with its 95% interval; a station-detail chart shows the full 2021–2026
   history; a "What is MMWQI?" explainer.

## Project layout

```
dosm_dashboard/
├── app/app.py                  the Streamlit app — the only thing that ships
├── data/processed/             clean CSVs + GeoJSON the app reads (already built)
├── data/raw/                   downloaded Malaysia state boundaries GeoJSON
├── notebooks/                  copies of your two source notebooks + their
│                                run outputs (forecast workbooks)
├── scripts/
│   ├── prepare_data.py         notebook outputs -> data/processed/*.csv
│   ├── geocode_stations.py     pass 1: OSM geocoding of the 188 MMWQI stations
│   ├── geocode_retry.py        pass 2: fixes cross-state mismatches, state-scoped retry
│   ├── fix_station_coords.py   validates passes 1-2, falls back to a jittered
│   │                            state-centroid point where geocoding failed
│   ├── apply_google_fixes.py   pass 3: applies data/raw/google_maps_fixes.csv
│   │                            (hand-verified via Google Maps for the ~90
│   │                            stations OSM still got wrong/missing — see
│   │                            below), re-validated against state boundaries
│   ├── audit_coords.py         final sweep over all 188 final coordinates:
│   │                            state-polygon containment, within-state
│   │                            outlier distance, and a Penang island-vs-
│   │                            mainland name/coordinate consistency check
│   └── prepare_ctrs.py         TSRI_CTRS_model.xlsx -> data/processed/ctrs_summary.csv
│                                + ctrs_settings.csv (a straight read of the
│                                precomputed CTRS_Summary sheet, no recomputation)
└── requirements.txt
```

## Running it yourself

```bash
pip install -r requirements.txt
streamlit run app/app.py
```

Opens at `http://localhost:8501`.

If you change the source Excel files or re-run the notebooks, regenerate the
processed data with:

```bash
python scripts/prepare_data.py
```

(Geocoding is slow — rate-limited to ~1 request/second against OpenStreetMap
— so `geocode_stations.py` / `geocode_retry.py` only need to be re-run if you
add or rename stations. `shapely` is needed for that step only: `pip install
shapely`.)

## Deploying so the jury needs zero setup

**Streamlit Community Cloud (free, recommended):**

1. Push this whole `dosm_dashboard/` folder to a GitHub repo.
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with
   GitHub, "New app", point it at the repo and set the main file to
   `app/app.py`.
3. Deploy. You get a public URL (`https://<something>.streamlit.app`) — the
   jury just opens it in any browser, no install, no login.

That's it — no server to maintain, and it redeploys automatically if you
push more commits before the submission deadline.

## Data notes / caveats (worth keeping in your written report)

- **Tourism forecasts (2026–2028)** are model output, not published DOSM
  statistics. State-level totals use an ensemble of 3 methods (recursive ML,
  damped drift, log-linear recovery trend); the state-of-origin → destination
  breakdown for a single state uses the single best-performing ML model only
  (that breakdown isn't ensembled). This is disclosed in-app.
- **MMWQI forecasts (2026)** use the best-backtested simple smoothing method
  per station (chosen by holdout backtest on 2025), with a 95% interval from
  the backtest residual spread — not a formal statistical confidence
  interval. Five years of data per station is very little to forecast from;
  treat the interval as the real output, not the point estimate.
- **Station coordinates**: the MMWQI workbook has no GPS coordinates, only
  station/area names. OpenStreetMap/Nominatim geocoding alone only placed
  100 of 188 (53%) confidently — and a few of those were wrong in an easy-to-miss
  way, e.g. "Batu Maung" (a beach on Penang **island**) landing on the Penang
  **mainland** because a nearby, similarly-named place won the search. Every
  station OSM missed or misplaced was re-checked by hand against Google Maps
  (`data/raw/google_maps_fixes.csv`), each fix re-validated against its
  state's actual polygon (not just trusted blindly) before being accepted.
  That brought confidently-placed stations to **182 of 188 (97%)**. A final
  automated audit (`audit_coords.py`) then re-checked all 188 final points —
  not just the ones just fixed — against their own state's polygon and against
  their neighbours' spread, and caught two more real errors purely by
  geometry: one station whose OSM match had literally matched a Kota
  Kinabalu *street* named "Jalan Johor" (containing the substring "Johor",
  which fooled the state-name text check), and a cluster of "Teluk Brunei"
  stations placed in open water just outside the Sabah polygon. Both were
  corrected against Google Maps and re-verified. The remaining 6 (beaches
  whose name collides with a same-named beach in another state, with no
  confident match anywhere) fall back to their state's centroid with a small
  offset, and are visibly marked in the app (fainter pin, "location
  approximate" in the hover). The `precision` column in
  `data/processed/mmwqi_station_coords_fixed.csv` records which is which.
  This is disclosed in-app rather than presented as exact GPS fixes.
- **CTRS/TSRI (Coastal Tourism Risk Score)** is read directly from your
  `TSRI_CTRS_model.xlsx` workbook's `CTRS_Summary` sheet — the app trusts it
  as the source of truth and does not re-derive X/Y/Z or the weights. If you
  change anything in the workbook (control-panel settings, input data), copy
  the updated file into `notebooks/TSRI_CTRS_model.xlsx` and re-run
  `python scripts/prepare_ctrs.py` before redeploying. Perlis is excluded
  (no MMWQI station); the workbook's own caveats (LCC-missing treatment,
  equal weights, MPA overlap, proxy exposure measure) are summarised in the
  app's "Data caveats" expander on that tab and are worth repeating in your
  written report.
