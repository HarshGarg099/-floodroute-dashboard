import json
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="FloodRoute | Flood Intelligence", page_icon="🌊", layout="wide")

# Files placed in the "data" folder next to this app load automatically.
DATA = Path(__file__).parent / "data"

# Saved results from the FloodRoute notebook (demo only, not live conditions).
DEMO = {
    "flood_ha": 12503,
    "flagged_segments": 52,
    "total_segments": 17213,
    "normal_km": 23.3,
    "safe_km": 29.8,
    "normal_flagged_crossed": 2,
    "safe_flagged_crossed": 0,
    "trips_tested": 247,
    "trips_affected": 15,
    "median_detour_pct": 3,
    "osm_places": 35,
    "places_flood_overlap": 8,
    "places_not_safe_reachable": 0,
    "flagged_by_threshold": {"-15": 162, "-17": 52, "-19": 22},
    "area_range_ha": [7351, 19267],
}

st.markdown("""
<style>
.stApp { background: #0b1220; color: #edf4ff; }
.block-container { padding-top: 1.4rem; }
[data-testid="stMetric"] { background: #141f31; border: 1px solid #27364c; padding: 16px; border-radius: 14px; }
[data-testid="stMetricLabel"] { color: #9eb2cc; }
[data-testid="stMetricValue"] { color: #f4f8ff; }
.fr-sub { color: #a8bad0; }
.fr-card { background:#141f31; border:1px solid #27364c; border-radius:14px; padding:16px; }
</style>
""", unsafe_allow_html=True)


def get_bytes(upload, name):
    """Use the uploaded file if given, else the file in data/, else None."""
    if upload is not None:
        return upload.getvalue()
    path = DATA / name
    return path.read_bytes() if path.exists() else None


def get_json(upload, name):
    raw = get_bytes(upload, name)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        st.error(f"Could not read {name}: {e}")
        return None


def props_table(geojson):
    rows = []
    for i, feature in enumerate((geojson or {}).get("features", [])):
        rows.append({"Feature": i + 1, **(feature.get("properties") or {})})
    return pd.DataFrame(rows)


def centroid(geometry):
    """Rough centre of a Point / Polygon / LineString for map markers."""
    try:
        coords = geometry["coordinates"]
        if geometry["type"] == "Point":
            return coords[1], coords[0]
        while isinstance(coords[0][0], list):
            coords = coords[0]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        return sum(lats) / len(lats), sum(lons) / len(lons)
    except Exception:
        return None


st.title("🌊 FloodRoute")
st.markdown('<p class="fr-sub">Satellite flood mapping · road-risk screening · route comparison</p>', unsafe_allow_html=True)
st.warning("DEMONSTRATION DATA — Assam, July 2020. Not live flood monitoring. Possible flood overlap is not a confirmed road closure; verify with official sources and field teams.")

with st.sidebar:
    st.header("Dashboard controls")
    st.caption("Files in the app's data folder load automatically. Upload here only to replace them.")
    summary_upload = st.file_uploader("summary.json", type=["json"])
    roads_upload = st.file_uploader("flagged_roads.geojson", type=["geojson", "json"])
    routes_upload = st.file_uploader("example_routes.geojson", type=["geojson", "json"])
    villages_upload = st.file_uploader("villages_status.geojson", type=["geojson", "json"])
    rescue_upload = st.file_uploader("rescue_priority.csv", type=["csv"])
    map_upload = st.file_uploader("route_map_villages.html or flood_map.html", type=["html"])

summary = DEMO.copy()
loaded = get_json(summary_upload, "summary.json")
if isinstance(loaded, dict):
    summary.update(loaded)

flood_ha = summary.get("flood_ha", 0)
flagged = summary.get("flagged_segments", 0)
total = summary.get("total_segments", 0)
normal_km = summary.get("normal_km", 0)
safe_km = summary.get("safe_km")
pct = (100 * flagged / total) if total else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Estimated new inundation", f"{flood_ha:,} ha")
m2.metric("Possible road overlaps", f"{flagged:,}", f"{pct:.2f}% of segments", delta_color="off")
m3.metric("Normal route", f"{normal_km} km")
m4.metric("Flood-avoiding candidate", f"{safe_km} km" if safe_km is not None else "No route")

tab_overview, tab_map, tab_roads, tab_routes, tab_villages, tab_about = st.tabs(
    ["Overview", "Map", "Road risk", "Route comparison", "Villages & rescue", "About & limitations"]
)

with tab_overview:
    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("Flood-risk snapshot")
        st.markdown('<div class="fr-card">The notebook estimates newly inundated pixels by comparing Sentinel-1 VV backscatter before and after the event, excluding frequent permanent water and steep slopes. The area is an estimate and is not validated.</div>', unsafe_allow_html=True)
        st.write("")
        a, b = st.columns(2)
        a.metric("Road segments checked", f"{total:,}")
        b.metric("Sample trips tested", f"{summary.get('trips_tested', 0):,}")
        c, d = st.columns(2)
        c.metric("Trips crossing flagged segments", f"{summary.get('trips_affected', 0):,}")
        d.metric("Median detour (affected trips)", f"{summary.get('median_detour_pct', 0)}%")
        rng = summary.get("area_range_ha")
        if rng:
            st.caption(f"Flood area across tested thresholds: {rng[0]:,} to {rng[1]:,} ha.")
    with right:
        st.subheader("Threshold sensitivity")
        sens = summary.get("flagged_by_threshold") or DEMO["flagged_by_threshold"]
        if isinstance(sens, dict) and sens:
            keys = sorted(sens.keys(), key=lambda k: int(str(k).replace("dB", "").strip()))
            df = pd.DataFrame({
                "VV threshold": [f"{str(k).replace('dB', '').strip()} dB" for k in keys],
                "Flagged segments": [sens[k] for k in keys],
            })
            st.bar_chart(df.set_index("VV threshold"))
            st.caption("The number of flagged roads changes with the flood-detection threshold.")

with tab_map:
    st.subheader("Event map")
    raw = get_bytes(map_upload, "route_map_villages.html") or get_bytes(None, "flood_map.html")
    if raw:
        components.html(raw.decode("utf-8", errors="replace"), height=650, scrolling=True)
        st.caption("Map exported from the notebook. Earth Engine tiles may expire; basemap and vector layers stay visible.")
    else:
        st.info("Add route_map_villages.html or flood_map.html to the data folder (or upload it in the sidebar).")

with tab_roads:
    st.subheader("Possible road overlap review")
    st.write("A flagged segment intersects the estimated flood layer. It is a priority for verification, not proof that the road is closed.")
    st.metric("Flagged / all segments", f"{flagged:,} / {total:,}")
    df_roads = props_table(get_json(roads_upload, "flagged_roads.geojson"))
    if not df_roads.empty:
        search = st.text_input("Search road attributes", placeholder="e.g. primary, residential")
        if search:
            mask = df_roads.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
            df_roads = df_roads[mask]
        st.dataframe(df_roads, use_container_width=True, height=360)
        st.download_button("Download table (CSV)", df_roads.to_csv(index=False), "flagged_roads_table.csv", "text/csv")
    else:
        st.info("Add flagged_roads.geojson to the data folder to inspect flagged roads.")

with tab_routes:
    st.subheader("Route comparison")
    c1, c2 = st.columns(2)
    c1.metric("Normal shortest route", f"{normal_km} km", f"crosses {summary.get('normal_flagged_crossed', '?')} flagged segments", delta_color="off")
    c2.metric("Flood-avoiding candidate", f"{safe_km} km" if safe_km is not None else "Unavailable", f"crosses {summary.get('safe_flagged_crossed', '?')} flagged segments", delta_color="off")
    if safe_km is not None and normal_km:
        detour = (safe_km / normal_km - 1) * 100
        st.progress(min(max(detour / 100, 0.0), 1.0), text=f"Candidate route is {detour:.1f}% longer in this example")
        st.caption("The route avoids segments flagged by the model. It is not guaranteed safe or passable.")
    df_routes = props_table(get_json(routes_upload, "example_routes.geojson"))
    if not df_routes.empty:
        st.dataframe(df_routes, use_container_width=True)

with tab_villages:
    st.subheader("Villages and rescue priority")
    v1, v2, v3 = st.columns(3)
    v1.metric("OSM places checked", summary.get("osm_places", "-"))
    v2.metric("Possible flood overlap", summary.get("places_flood_overlap", "-"))
    v3.metric("Not reachable via safe network", summary.get("places_not_safe_reachable", "-"))

    rescue_raw = get_bytes(rescue_upload, "rescue_priority.csv")
    if rescue_raw:
        from io import BytesIO
        st.markdown("**Rescue priority** (safe-route distance and ETA from the base point; population from WorldPop, estimated)")
        st.dataframe(pd.read_csv(BytesIO(rescue_raw)), use_container_width=True)
    else:
        st.info("Add rescue_priority.csv to the data folder.")

    villages = get_json(villages_upload, "villages_status.geojson")
    if villages:
        points = []
        for feature in villages.get("features", []):
            pos = centroid(feature.get("geometry") or {})
            if pos:
                overlap = bool((feature.get("properties") or {}).get("flood_overlap"))
                points.append({"lat": pos[0], "lon": pos[1], "color": "#e5484d" if overlap else "#30a46c"})
        if points:
            st.markdown("**Village map** (red = possible flood overlap, green = none)")
            st.map(pd.DataFrame(points), latitude="lat", longitude="lon", color="color")

with tab_about:
    st.subheader("Data and method")
    st.markdown("""
- **Satellite:** Sentinel-1 SAR VV before/after composites.
- **Flood estimate:** dark post-event pixels with a minimum backscatter drop, excluding frequent permanent water and steep slopes.
- **Road network:** OpenStreetMap driving network; road corridors are checked against the flood mask.
- **Routing:** shortest path compared with a candidate path that excludes flagged segments.
- **Cross-check:** a Sentinel-2 water proxy and a threshold sensitivity analysis (indicative, not validation).
""")
    st.subheader("Important limitations")
    st.markdown("""
- The saved example is Assam, June–July 2020, not current conditions.
- Only 1 pre-event Sentinel-1 scene was available; agreement with the Sentinel-2 proxy is imperfect.
- A same-orbit check gave 12,204 ha, and only 9,580 ha (77%) overlaps the headline 12,503 ha.
- OpenStreetMap may be incomplete or outdated.
- A route not flagged by this model is **not automatically safe**.
- Population figures are model estimates (WorldPop).
- This is a demonstration decision-support prototype, not an operational emergency-service system.
- Always use official warnings, local authorities, and field verification for real decisions.
""")

st.divider()
st.caption("FloodRoute · ORBITRON Problem 17 · Dashboard demonstration")
