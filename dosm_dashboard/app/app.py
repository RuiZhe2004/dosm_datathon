import json
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Paths & page config
# ---------------------------------------------------------------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(APP_DIR, "..", "data", "processed")

st.set_page_config(page_title="Malaysia Tourism & Coastal Water Quality", layout="wide", page_icon="🗺️")

# Semantic colours for MMWQI quality categories (traffic-light style — kept
# distinct from the rest of the app's blue palette on purpose, since red vs.
# blue here carries meaning: bad vs. good water quality).
CAT_COLOR = {"Poor": "#b2182b", "Moderate": "#ef8a62", "Good": "#67a9cf", "Excellent": "#2166ac"}
CAT_ORDER = ["Poor", "Moderate", "Good", "Excellent"]

# House palette — everything that ISN'T a semantic MMWQI colour uses these blues.
BLUE_SEQUENCE = ["#08306b", "#08519c", "#2171b5", "#4292c6", "#6baed6", "#9ecae1", "#c6dbef", "#deebf7"]
BLUE_BAR = "#2171b5"
TREND_COLOR_MAP = {"actual": "#08519c", "forecast": "#6baed6"}

# CTRS risk severity also gets its own semantic scale (higher risk = darker
# red), same exception as the MMWQI traffic-light colours above.
RISK_SCALE = "OrRd"
XYZ_COLOR = {"Exposure (X)": "#e6550d", "Environmental stress (Y)": "#b2182b", "Protection (Z)": "#2166ac"}

ACTUAL_YEARS = list(range(2011, 2026))
FORECAST_YEARS = [2026, 2027, 2028]
YEAR_OPTIONS = [str(y) for y in ACTUAL_YEARS] + [f"{y} (Prediction)" for y in FORECAST_YEARS]
MMWQI_YEAR_OPTIONS = [str(y) for y in range(2021, 2026)] + ["2026 (Prediction)"]


def parse_year_option(opt):
    y = int(opt.split(" ")[0])
    return y, "Prediction" in opt


def centered_caption(text):
    """Like st.caption, but centered. `text` may contain <b>/<i>/<br> HTML tags."""
    st.markdown(
        f"<div style='text-align:center; color:rgba(49,51,63,0.6); "
        f"font-size:0.875rem; line-height:1.5;'>{text}</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Data loading (cached)
# ---------------------------------------------------------------------------
@st.cache_data
def load_geojson():
    with open(os.path.join(DATA, "malaysia_states.geojson"), encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_tourism():
    return pd.read_csv(os.path.join(DATA, "tourism_flows.csv"))


@st.cache_data
def load_national():
    return pd.read_csv(os.path.join(DATA, "tourism_national.csv"))


@st.cache_data
def load_mmwqi():
    return pd.read_csv(os.path.join(DATA, "mmwqi_long.csv"))


@st.cache_data
def load_mmwqi_wide():
    return pd.read_csv(os.path.join(DATA, "mmwqi_forecast_wide.csv"))


@st.cache_data
def load_coords():
    fixed = os.path.join(DATA, "mmwqi_station_coords_fixed.csv")
    raw = os.path.join(DATA, "mmwqi_station_coords.csv")
    path = fixed if os.path.exists(fixed) else raw
    if not os.path.exists(path):
        return pd.DataFrame(columns=["station", "lat", "lon", "precision"])
    df = pd.read_csv(path)
    if "precision" not in df.columns:
        df["precision"] = "geocoded"
    return df[["station", "lat", "lon", "precision"]]


@st.cache_data
def load_ctrs():
    return pd.read_csv(os.path.join(DATA, "ctrs_summary.csv"))


@st.cache_data
def load_ctrs_settings():
    return pd.read_csv(os.path.join(DATA, "ctrs_settings.csv"), index_col=0)["value"]


geojson = load_geojson()
tourism = load_tourism()
national = load_national()
mmwqi = load_mmwqi()
mmwqi_wide = load_mmwqi_wide()
coords = load_coords()
ctrs = load_ctrs()
ctrs_settings = load_ctrs_settings()

STATE_LIST = sorted({f["properties"]["canonical_state"] for f in geojson["features"]})
STATION_STATE = mmwqi.drop_duplicates("station").set_index("station")["state_canon"]
MMWQI_STATE_LIST = sorted(mmwqi["state_canon"].dropna().unique().tolist())
CTRS_STATE_LIST = sorted(ctrs["state_canon"].dropna().unique().tolist())

st.title("Malaysia Domestic Tourism & Coastal Water Quality Dashboard")

tab_tourism, tab_ctrs, tab_mmwqi = st.tabs([
    "Domestic Tourism", "Coastal Tourism Risk (CTRS)", "Coastal Water Quality (MMWQI)",
])

# ===========================================================================
# TAB 1 — Domestic tourism
# ===========================================================================
with tab_tourism:
    c1, c2 = st.columns(2)
    with c1:
        origin_choice = st.selectbox(
            "State of origin", ["All states (Malaysia total)"] + STATE_LIST, key="t1_origin",
        )
    with c2:
        year_choice = st.selectbox("Year", YEAR_OPTIONS, index=len(ACTUAL_YEARS) - 1, key="t1_year")

    year, is_forecast = parse_year_option(year_choice)

    if origin_choice == "All states (Malaysia total)":
        if is_forecast:
            sub = tourism[(tourism.kind == "forecast_ensemble_total") & (tourism.year == year)]
        else:
            sub = tourism[(tourism.kind == "actual") & (tourism.year == year)]
        dest_col = "destination_canon"
    else:
        kind = "forecast_ml" if is_forecast else "actual"
        sub = tourism[(tourism.kind == kind) & (tourism.year == year)
                      & (tourism.origin_canon == origin_choice)]
        dest_col = "destination_canon"

    state_totals = sub.groupby(dest_col, as_index=False)["visitors"].sum()
    state_totals = state_totals.rename(columns={dest_col: "canonical_state"})
    state_totals = pd.DataFrame({"canonical_state": STATE_LIST}).merge(state_totals, how="left").fillna(0)

    map_col, side_col = st.columns([2, 1])

    with map_col:
        fig = px.choropleth_map(
            state_totals, geojson=geojson, locations="canonical_state",
            featureidkey="properties.canonical_state", color="visitors",
            color_continuous_scale="Blues", map_style="carto-positron",
            zoom=4.6, center={"lat": 4.2, "lon": 109.0}, opacity=0.85,
            labels={"visitors": "Visitors ('000)"},
            hover_name="canonical_state", hover_data={"canonical_state": False, "visitors": True},
        )
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=520)
        title_bit = "Predicted" if is_forecast else "Observed"
        centered_caption(
            f"{title_bit} tourists received by state — origin: <b>{origin_choice}</b>, year: <b>{year}</b>"
            + (" <i>(model forecast)</i>" if is_forecast else "")
        )
        st.plotly_chart(fig, width="stretch", key="tourism_map")

    with side_col:
        top10 = state_totals.sort_values("visitors", ascending=False).head(10)
        bar = px.bar(
            top10.sort_values("visitors"), x="visitors", y="canonical_state", orientation="h",
            labels={"visitors": "Visitors ('000)", "canonical_state": ""}, title="Top destination states",
        )
        bar.update_traces(marker_color=BLUE_BAR)
        bar.update_layout(height=280, margin=dict(l=0, r=10, t=40, b=0))
        st.plotly_chart(bar, width="stretch")

        ranked = state_totals.sort_values("visitors", ascending=False)
        if len(ranked) > 5:
            pie_df = pd.concat([
                ranked.head(5),
                pd.DataFrame([{"canonical_state": "Other states", "visitors": ranked.iloc[5:]["visitors"].sum()}]),
            ], ignore_index=True)
        else:
            pie_df = ranked
        pie = px.pie(pie_df, names="canonical_state", values="visitors", title="Share of destinations", hole=0.4,
                    color_discrete_sequence=BLUE_SEQUENCE)
        pie.update_layout(height=280, margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(pie, width="stretch")

    st.divider()

    c3, c4 = st.columns(2)
    with c3:
        st.markdown(f"**State of origin:** {origin_choice}")
    with c4:
        visited_choice = st.selectbox(
            "State visited", ["All states (total)"] + STATE_LIST, key="t1_visited",
        )

    st.subheader(f"Trend: {origin_choice} → {visited_choice}")

    def _actual_forecast(kind_actual, kind_forecast, origin_filter=None, dest_filter=None, group_by_year=False):
        a = tourism[tourism.kind == kind_actual]
        f = tourism[tourism.kind == kind_forecast]
        if origin_filter is not None:
            a = a[a.origin_canon == origin_filter]
            f = f[f.origin_canon == origin_filter]
        if dest_filter is not None:
            a = a[a.destination_canon == dest_filter]
            f = f[f.destination_canon == dest_filter]
        if group_by_year:
            a = a.groupby("year", as_index=False)["visitors"].sum()
            f = f.groupby("year", as_index=False)["visitors"].sum()
        else:
            a = a[["year", "visitors"]]
            f = f[["year", "visitors"]]
        a = a.assign(kind="actual")
        f = f.assign(kind="forecast")
        return pd.concat([a, f], ignore_index=True).sort_values("year")

    if origin_choice == "All states (Malaysia total)" and visited_choice == "All states (total)":
        trend = national.copy()
        trend["kind"] = trend["kind"].replace({"forecast_ensemble_total": "forecast"})
    elif origin_choice == "All states (Malaysia total)":
        trend = _actual_forecast("actual", "forecast_ensemble_total", dest_filter=visited_choice, group_by_year=True)
    elif visited_choice == "All states (total)":
        trend = _actual_forecast("actual", "forecast_ml", origin_filter=origin_choice, group_by_year=True)
    else:
        trend = _actual_forecast("actual", "forecast_ml", origin_filter=origin_choice, dest_filter=visited_choice)

    line = px.line(trend, x="year", y="visitors", color="kind", markers=True,
                   color_discrete_map=TREND_COLOR_MAP,
                   labels={"visitors": "Visitors ('000)", "year": "Year"})
    line.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(line, width="stretch")

    centered_caption(
        "Actual figures: Domestic Tourism Survey (DTS), DOSM, Table 10, 2011–2025.<br>"
        "2026–2028 figures are model forecasts, not published statistics.<br>"
        "State totals use an ensemble of 3 methods (recursive ML + damped drift + log-linear recovery "
        "trend); the origin-to-destination breakdown for one state uses the single best-performing ML "
        "model only."
    )

# ===========================================================================
# TAB 3 (visually) — MMWQI
# ===========================================================================
with tab_mmwqi:
    c1, c2 = st.columns(2)
    with c1:
        focus = st.selectbox("State", ["All states"] + MMWQI_STATE_LIST, key="t2_state")
    with c2:
        m_year_choice = st.selectbox("Year", MMWQI_YEAR_OPTIONS, index=len(MMWQI_YEAR_OPTIONS) - 2, key="t2_year")

    m_year, m_is_forecast = parse_year_option(m_year_choice)

    snap = mmwqi[mmwqi.year == m_year].drop(columns=["lower_95", "upper_95"]).copy()
    snap = snap.merge(coords, on="station", how="left")
    snap = snap.merge(mmwqi_wide[["station", "pred_2026", "lower_95", "upper_95"]], on="station", how="left")
    snap = snap.dropna(subset=["lat", "lon"])

    if focus != "All states":
        snap = snap[snap.state_canon == focus]

    if snap.empty:
        st.warning("No geocoded stations to show yet — the geocoding step may still be running.")
    else:
        snap["hover"] = (
            "<b>" + snap["area"].astype(str) + "</b><br>" + snap["station"].astype(str)
            + "<br>" + str(m_year) + " MMWQI: " + snap["mmwqi"].round(1).astype(str)
            + " (" + snap["category"].astype(str) + ")"
            + "<br>2026 forecast: " + snap["pred_2026"].round(1).astype(str)
            + " [" + snap["lower_95"].round(1).astype(str) + "–" + snap["upper_95"].round(1).astype(str) + "]"
            + snap["precision"].map({
                "state_approx": "<br><i>location approximate (state-level)</i>", "geocoded": "",
            }).fillna("")
        )

        fig2 = go.Figure()
        for cat in CAT_ORDER:
            for prec, size, opacity in [("geocoded", 11, 0.95), ("state_approx", 8, 0.55)]:
                d = snap[(snap.category == cat) & (snap.precision == prec)]
                if d.empty:
                    continue
                fig2.add_trace(go.Scattermap(
                    lat=d.lat, lon=d.lon, mode="markers",
                    marker=dict(size=size, color=CAT_COLOR[cat], opacity=opacity),
                    name=cat, legendgroup=cat, showlegend=(prec == "geocoded"),
                    text=d.hover, hoverinfo="text",
                ))

        if focus != "All states" and len(snap) > 0:
            center = {"lat": float(snap.lat.mean()), "lon": float(snap.lon.mean())}
            zoom = 8.0
        else:
            center = {"lat": 4.2, "lon": 109.0}
            zoom = 4.6

        fig2.update_layout(
            map=dict(style="carto-positron", center=center, zoom=zoom),
            margin=dict(l=0, r=0, t=0, b=0), height=560,
            legend=dict(orientation="h", yanchor="bottom", y=1.01),
        )
        st.plotly_chart(fig2, width="stretch")
        centered_caption(
            f"{len(snap)} station(s) shown; The pin colour indicates {m_year} MMWQI category.<br>"
            "Hover a pin to see the current value and the 2026 forecast with its 95% interval.<br>"
            "Coordinates are geocoded from station area names (OpenStreetMap) — approximate, "
            "not the surveyor's exact GPS fix."
        )

    st.divider()
    if focus != "All states":
        station_list = sorted([s for s in mmwqi_wide["station"] if STATION_STATE.get(s) == focus])
    else:
        station_list = sorted(mmwqi_wide["station"].unique().tolist())

    if not station_list:
        st.info("No stations for this state.")
    else:
        label_map = mmwqi_wide.set_index("station")["area"].to_dict()
        pick = st.selectbox(
            "Station detail", station_list,
            format_func=lambda s: f"{label_map.get(s, s)} ({s})", key="t2_station",
        )
        row = mmwqi_wide[mmwqi_wide.station == pick].iloc[0]
        hist_cols = [c for c in mmwqi_wide.columns if c.startswith("mmwqi_")]
        years = [int(c.replace("mmwqi_", "")) for c in hist_cols]
        vals = [row[c] for c in hist_cols]
        detail = pd.DataFrame({
            "year": years + [2026], "mmwqi": vals + [row["pred_2026"]],
            "kind": ["actual"] * len(years) + ["forecast"],
        })
        fig3 = px.line(detail, x="year", y="mmwqi", color="kind", markers=True,
                       color_discrete_map=TREND_COLOR_MAP, title=f"{row['area']} ({pick})")
        fig3.add_hrect(y0=row["lower_95"], y1=row["upper_95"], x0=2025.5, x1=2026.5,
                      fillcolor="grey", opacity=0.2, line_width=0)
        for band, lbl in [(90, "Excellent"), (80, "Good"), (51, "Moderate")]:
            fig3.add_hline(y=band, line_dash="dot", line_color="grey",
                          annotation_text=lbl, annotation_position="right")
        fig3.update_layout(height=340, margin=dict(l=0, r=0, t=40, b=0), yaxis_range=[40, 102])
        st.plotly_chart(fig3, width="stretch")

    centered_caption(
        "Malaysian Marine Water Quality Index (MMWQI), Department of Environment (DOE), 2021–2025.<br>"
        "2026 forecast uses the best-backtested simple smoothing method per station; Shaded band = "
        "95% prediction interval from backtest residuals, not a formal confidence interval."
    )

    st.divider()
    st.subheader("What is MMWQI?")
    st.markdown(
        "The **Malaysian Marine Water Quality Index (MMWQI)** is the Department of Environment's "
        "official tool for communicating the state of Malaysia's marine waters in a single, easy-to-read "
        "number instead of a table of raw lab readings. It combines six water quality parameters — "
        "**Dissolved Oxygen, Faecal Coliform, Ammonia, Nitrate, Phosphate, and Total Suspended "
        "Solids** — chosen because they matter most for protecting marine ecosystems, respond "
        "sensitively to pollution, and are routinely measured at DOE's monitoring stations. Each "
        "parameter is converted to a sub-index and combined into one weighted score from 0 to 100, "
        "which is then classified as **Excellent (90–100), Good (80–89), Moderate (50–79), or Poor "
        "(0–49)**. Because an index can't capture every aspect of water quality on its own, DOE "
        "recommends reading the MMWQI alongside the underlying parameter data for a fuller picture."
    )

# ===========================================================================
# TAB 2 (visually) — CTRS / TSRI coastal tourism risk index
# ===========================================================================
with tab_ctrs:
    st.markdown(
        "Coastal Tourism Risk Score (CTRS) / Tourism Sensitivity Risk Index (TSRI) is a composite "
        "index per state combining tourism exposure, environmental stress and marine protection. "
        "Higher value means higher risk in the state."
    )

    map_col, side_col = st.columns([2, 1])

    ctrs_map_df = pd.DataFrame({"canonical_state": STATE_LIST}).merge(
        ctrs[["state_canon", "tsri_0_1", "rank"]], left_on="canonical_state", right_on="state_canon", how="left",
    )

    with map_col:
        fig_ctrs = px.choropleth_map(
            ctrs_map_df, geojson=geojson, locations="canonical_state",
            featureidkey="properties.canonical_state", color="tsri_0_1",
            color_continuous_scale=RISK_SCALE, map_style="carto-positron",
            zoom=4.6, center={"lat": 4.2, "lon": 109.0}, opacity=0.85,
            labels={"tsri_0_1": "TSRI (0–1)"},
            hover_name="canonical_state", hover_data={"canonical_state": False, "tsri_0_1": ":.3f", "rank": True},
        )
        fig_ctrs.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=520)
        st.plotly_chart(fig_ctrs, width="stretch", key="ctrs_map")

    with side_col:
        ranked_ctrs = ctrs.sort_values("tsri_0_1")
        bar_ctrs = px.bar(
            ranked_ctrs, x="tsri_0_1", y="state_canon", orientation="h", color="tsri_0_1",
            color_continuous_scale=RISK_SCALE,
            labels={"tsri_0_1": "TSRI (0–1)", "state_canon": ""}, title="Risk ranking (all 13 scored states)",
        )
        bar_ctrs.update_layout(height=460, margin=dict(l=0, r=10, t=40, b=0), coloraxis_showscale=False)
        st.plotly_chart(bar_ctrs, width="stretch")

    centered_caption(
        "Coastal tourism risk (TSRI, 0–1) by state<br>"
        "Darker colour means higher risk.<br>"
        "Grey states have no score: Perlis has no MMWQI monitoring station so it is excluded from "
        "the index; Kuala Lumpur, Putrajaya and Sarawak's non-coastal neighbours are landlocked "
        "and not part of the underlying model."
    )

    st.divider()
    focus_ctrs = st.selectbox("State", CTRS_STATE_LIST, key="t3_state")
    row = ctrs[ctrs.state_canon == focus_ctrs].iloc[0]

    m1, m2, m3 = st.columns(3)
    m1.metric("Rank (of 13)", f"{int(row['rank'])}")
    m2.metric("TSRI", f"{row['tsri']:.3f}")
    m3.metric("TSRI (0–1)", f"{row['tsri_0_1']:.3f}")

    xyz_df = pd.DataFrame({
        "component": ["Exposure (X)", "Environmental stress (Y)", "Protection (Z)"],
        "value": [row["x_exposure"], row["y_stress"], row["z_protection"]],
    })
    fig_xyz = px.bar(xyz_df, x="component", y="value", color="component", color_discrete_map=XYZ_COLOR,
                     labels={"value": "Normalised value (0–1)", "component": ""},
                     title=f"{focus_ctrs}: risk components")
    fig_xyz.update_layout(height=320, margin=dict(l=0, r=0, t=40, b=0), showlegend=False, yaxis_range=[0, 1])
    st.plotly_chart(fig_xyz, width="stretch")

    LCC_NOTE_DISPLAY = {"no LCC data: substituted (ZERO)": "No LCC data: Substituted with ZERO"}
    w_x, w_y, w_z = float(ctrs_settings["w_x"]), float(ctrs_settings["w_y"]), float(ctrs_settings["w_z"])
    if pd.notna(row["lcc_note"]):
        note_text = LCC_NOTE_DISPLAY.get(row["lcc_note"], row["lcc_note"])
        note = f"<br><i>{note_text}</i>"
    else:
        note = ""
    centered_caption(f"TSRI = {w_x:.2f}·X + {w_y:.2f}·Y − {w_z:.2f}·Z{note}")

    st.divider()
    st.subheader("What is CTRS / TSRI?")
    st.markdown(
        "The **Coastal Tourism Risk Score (CTRS)**, expressed as the **Tourism Sensitivity Risk Index "
        "(TSRI)**, combines three things for each coastal state:\n"
        "- **Exposure (X)** — how much of the state's tourism is concentrated on the coast, estimated "
        "from the beach-hotel share of all hotels multiplied by domestic tourist volume.\n"
        "- **Environmental stress (Y)** — a blend of water quality (`1 − MMWQI/100`) and reef health "
        "(`1 − Live Coral Cover %`), so a lower MMWQI or less coral cover raises stress.\n"
        "- **Protection (Z)** — the share of the state's marine area that sits inside a protected "
        "marine park, weighted by how restrictive the protection is.\n\n"
        "These combine as **TSRI = w·X + w·Y − w·Z**: exposure and stress push risk up, protection "
        "pulls it down. All three are normalised to 0–1 first, so no single input can dominate just "
        "because it's measured on a bigger scale."
    )

    with st.expander("Data caveats"):
        st.markdown(
            "- **Perlis is excluded** from this index. It has no MMWQI monitoring station and cannot "
            "be scored. Please expect 13 of 14 Peninsular/Sabah/Sarawak states in the ranking, not 14.\n"
            "- **Missing coral-cover (LCC) data is treated as maximum coral stress**, a conservative "
            "choice, not left blank. This affects Kelantan, Selangor, Penang and Labuan, flagged above "
            "when selected. Please expect these states' ranking to shift under an alternative "
            "treatment.\n"
            "- **Equal weights are used**: ⅓ each for X, Y and Z, and 50/50 for MMWQI vs. coral cover "
            "within Y. Please expect a weighting sensitivity check before treating the exact ranking "
            "as final.\n"
            "- **Exposure (X) is a proxy**, not a direct count: beach-hotel share stands in for the "
            "share of tourists actually at the coast. Please treat X as an estimate of exposure, not "
            "a measured value.\n"
            "- **Protected-area overlaps (Z numerator) and shared marine-area sites split 50/50 "
            "between states (Z denominator) are simplifying assumptions.** Please expect a GIS-based "
            "estimate to differ from the figures shown here."
        )
