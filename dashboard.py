# dashboard.py
import streamlit as st
import pandas as pd
import requests
import altair as alt
import pydeck as pdk
import re
from typing import List, Dict, Any
from functools import lru_cache
from datetime import datetime, timedelta

API_URL = "http://127.0.0.1:8000"  # adjust if needed

st.set_page_config(page_title="CPSC Recalls Dashboard", layout="wide", initial_sidebar_state="expanded")

# ---------------------------
# Helpers
# ---------------------------
def safe_get_json(path: str, params: dict = None, timeout: int = 10) -> Any:
    url = f"{API_URL.rstrip('/')}{path}"
    try:
        r = requests.get(url, params=params or {}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Error fetching {url}: {e}")
        return None

@st.cache_data(ttl=300)
def fetch_recall_detail(recall_number: str) -> Dict[str, Any]:
    """Cached call to /recalls/{recall_number} to resolve names when top_* keys are recall ids."""
    url = f"{API_URL}/recalls/{recall_number}"
    try:
        r = requests.get(url, timeout=6)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}

def looks_like_recall_id(s: str) -> bool:
    if not isinstance(s, str):
        return False
    # Typical pattern observed: 2-3 digits dash 3 digits (example: 25-479 or 96-125) - be permissive
    return bool(re.match(r"^\d{1,3}[-/]\d{2,4}$", s)) or bool(re.match(r"^\d{2,4}$", s))

def resolve_label(key: str, kind: str = "manufacturer") -> str:
    """
    If `key` looks like a recall_number, try to fetch the recall and return the first manufacturer / sold_at.
    Otherwise return key unchanged.
    """
    if not key:
        return key
    if looks_like_recall_id(key):
        detail = fetch_recall_detail(key)
        if kind == "manufacturer":
            vals = detail.get("manufacturers") or detail.get("manufacturer") or []
            if isinstance(vals, list) and vals:
                return vals[0]
            elif isinstance(vals, str) and vals.strip():
                return vals.strip()
        elif kind == "seller":
            vals = detail.get("sold_at") or detail.get("soldat") or []
            if isinstance(vals, list) and vals:
                return vals[0]
            elif isinstance(vals, str) and vals.strip():
                return vals.strip()
    return key

def to_readable_date(val) -> str:
    """
    Robust conversion to readable date string.
    Accepts:
    - int (days since 1840-12-31)
    - ISO date string
    - datetime.date/datetime
    - None -> return empty string
    """
    if val is None:
        return ""
    # If integer: treat as days since 1840-12-31 (HOROLOG style used earlier)
    if isinstance(val, int):
        try:
            base = datetime(1840, 12, 31)
            dt = base + timedelta(days=val)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return str(val)
    # if already a date/datetime
    if isinstance(val, (datetime, )):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, str):
        # try parse
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%B %d, %Y"):
            try:
                return datetime.strptime(val, fmt).strftime("%Y-%m-%d")
            except Exception:
                pass
        # fallback: return original
        return val
    return str(val)

# ---------------------------
# Sidebar / Filters
# ---------------------------
st.sidebar.header("Filters")
manufacturer_filter = st.sidebar.text_input("Manufacturer (partial)")
country_filter = st.sidebar.text_input("Country (partial, ex: USA)")
source_filter = st.sidebar.text_input("Source (partial, ex: recall/warning)")

st.sidebar.markdown("---")
st.sidebar.markdown("API base: " + API_URL)
st.sidebar.caption("Data refreshed every 5 minutes (cached).")

# ---------------------------
# Fetch summary (with spinner)
# ---------------------------
with st.spinner("Fetching summary..."):
    summary = safe_get_json("/insights/summary")
    # fallback structure if endpoint missing
    if not summary:
        summary = {}

# ---------------------------
# Top Metrics Row
# ---------------------------
st.title("CPSC Recalls Dashboard — Advanced")
st.markdown("Interactive analysis of CPSC recalls and product safety warnings.")

col1, col2, col3 = st.columns([1.2, 1.2, 1.0])

total_recalls = summary.get("total_recalls") or 0
avg_units = summary.get("avg_units") or 0
# Com a nova API otimizada:
recalls_by_country = summary.get("recalls_by_country") or {}

# Total de países afetados e país mais afetado
countries_affected = summary.get("countries_affected") or 0
top_country = summary.get("top_country") or "N/A"

col1.metric("Total Recalls", f"{total_recalls:,}")
col2.metric("Average Units per Recall", f"{avg_units:,}")
col3.metric("Most affected", countries_affected)

# ---------------------------
# Top Manufacturers & Sellers
# ---------------------------
st.subheader("Top Manufacturers & Sellers")

# Top manufacturers from summary (dict name->count or sometimes recall_number->count)
top_man = summary.get("top_manufacturers") or {}
top_sellers = summary.get("top_sellers") or {}

def build_labelled_df(dct: Dict[str,int], kind: str="manufacturer", top_n: int=12) -> pd.DataFrame:
    items = []
    for k, v in dct.items():
        label = resolve_label(k, "manufacturer" if kind=="manufacturer" else "seller")
        items.append((label, int(v or 0)))
    df = pd.DataFrame(items, columns=[ "Name", "Count"])
    df = df.groupby("Name", as_index=False).sum().sort_values("Count", ascending=True).tail(top_n)
    return df

with st.spinner("Building manufacturer & seller charts..."):
    df_man = build_labelled_df(top_man, kind="manufacturer", top_n=12)
    df_sellers = build_labelled_df(top_sellers, kind="seller", top_n=12)

left_col, right_col = st.columns(2)
with left_col:
    st.markdown("**Top Manufacturers**")
    if df_man.empty:
        st.info("No manufacturer data available.")
    else:
        chart_m = alt.Chart(df_man).mark_bar().encode(
            x=alt.X("Count:Q", title="Number of Recalls"),
            y=alt.Y("Name:N", sort='-x', title="Manufacturer")
        ).properties(height=420, width=700)
        st.altair_chart(chart_m, use_container_width=True)

with right_col:
    st.markdown("**Top Sellers**")
    if df_sellers.empty:
        st.info("No sellers data available.")
    else:
        chart_s = alt.Chart(df_sellers).mark_bar(color="#ff7f0e").encode(
            x=alt.X("Count:Q", title="Number of Recalls"),
            y=alt.Y("Name:N", sort='-x', title="Seller")
        ).properties(height=420, width=700)
        st.altair_chart(chart_s, use_container_width=True)

# ---------------------------
# Recalls Over Time (by month)
# ---------------------------
st.subheader("Recalls Over Time")
with st.spinner("Loading recalls over time..."):
    by_month = safe_get_json("/insights/by_month") or {}
    # Expecting list/dict of month->count. Accept many shapes.
    # If by_month is list of dicts -> normalize.
    if isinstance(by_month, dict):
        df_month = pd.DataFrame(list(by_month.items()), columns=["month", "count"])
    elif isinstance(by_month, list):
        df_month = pd.DataFrame(by_month)
        if "name" in df_month.columns and "count" in df_month.columns:
            df_month = df_month.rename(columns={"name":"month"})
    else:
        df_month = pd.DataFrame(columns=["month","count"])

    if df_month.empty:
        st.info("No monthly data available.")
    else:
        df_month = df_month.sort_values("month")
        chart_month = alt.Chart(df_month).mark_line(point=True).encode(
            x=alt.X("month:N", title="Month"),
            y=alt.Y("count:Q", title="Number of Recalls")
        ).properties(width=900, height=350)
        st.altair_chart(chart_month, use_container_width=True)

# ---------------------------
# Recalls by Country
# ---------------------------
st.subheader("Recalls by Country")
with st.spinner("Loading recalls by country..."):
    by_country = safe_get_json("/insights/by_country") or {}
    # Accept dict or list-of-dicts
    if isinstance(by_country, dict):
        df_country = pd.DataFrame(list(by_country.items()), columns=["country", "count"])
    elif isinstance(by_country, list):
        df_country = pd.DataFrame(by_country)
        if "name" in df_country.columns and "count" in df_country.columns:
            df_country = df_country.rename(columns={"name":"country"})
    else:
        df_country = pd.DataFrame(columns=["country","count"])

    if df_country.empty:
        st.info("No country data available.")
    else:
        df_country = df_country.sort_values("count", ascending=False).head(25)
        st.bar_chart(df_country.set_index("country"))

# ---------------------------
# Remedy Types
# ---------------------------
st.subheader("Recalls by Remedy Type")
with st.spinner("Loading remedies..."):
    by_remedy = safe_get_json("/insights/by_remedy_type") or {}
    if isinstance(by_remedy, dict):
        df_remedy = pd.DataFrame(list(by_remedy.items()), columns=["remedy","count"])
    elif isinstance(by_remedy, list):
        df_remedy = pd.DataFrame(by_remedy)
        if "name" in df_remedy.columns and "count" in df_remedy.columns:
            df_remedy = df_remedy.rename(columns={"name":"remedy"})
    else:
        df_remedy = pd.DataFrame(columns=["remedy","count"])

    if df_remedy.empty:
        st.info("No remedy data available.")
    else:
        st.altair_chart(
            alt.Chart(df_remedy.sort_values("count", ascending=False).head(12)).mark_bar().encode(
                x=alt.X("count:Q", title="Number of Recalls"),
                y=alt.Y("remedy:N", sort='-x', title="Remedy Type")
            ).properties(height=320),
            use_container_width=True
        )

# ---------------------------
# Hazards Top
# ---------------------------
st.subheader("Top Hazards / Hazard Descriptions")
with st.spinner("Loading hazards..."):
    by_hazard = safe_get_json("/insights/by_hazard") or {}
    if isinstance(by_hazard, dict):
        df_hazard = pd.DataFrame(list(by_hazard.items()), columns=["hazard","count"])
    elif isinstance(by_hazard, list):
        df_hazard = pd.DataFrame(by_hazard)
        if "name" in df_hazard.columns and "count" in df_hazard.columns:
            df_hazard = df_hazard.rename(columns={"name":"hazard"})
    else:
        df_hazard = pd.DataFrame(columns=["hazard","count"])

    if df_hazard.empty:
        st.info("No hazard data available.")
    else:
        st.altair_chart(
            alt.Chart(df_hazard.sort_values("count", ascending=False).head(12)).mark_bar().encode(
                x=alt.X("count:Q", title="Number of Recalls"),
                y=alt.Y("hazard:N", sort='-x', title="Hazard")
            ).properties(height=320),
            use_container_width=True
        )

# ---------------------------
# Latest Recalls Table with Filters
# ---------------------------
st.subheader("Latest Recalls (filterable)")
params = {"page": 1, "page_size": 200, "manufacturer": manufacturer_filter, "country": country_filter, "source": source_filter}

with st.spinner("Fetching latest recalls..."):
    latest = safe_get_json("/recalls/", params=params) or []
    if isinstance(latest, dict) and "detail" in latest:
        st.error(latest.get("detail"))
        latest = []
    df_latest = pd.DataFrame(latest)

if df_latest.empty:
    st.info("No recalls to show.")
else:
    # normalize date column to readable
    if "recall_date" in df_latest.columns:
        df_latest["recall_date_readable"] = df_latest["recall_date"].apply(to_readable_date)
    # ensure manufacturers and sold_at are lists
    for col in ["manufacturers", "sold_at"]:
        if col in df_latest.columns:
            df_latest[col] = df_latest[col].apply(lambda x: ", ".join(x) if isinstance(x, list) else (x or ""))

    show_cols = ["recall_number", "product_safety_warning_number", "name_of_product", "recall_date_readable", "source", "units", "manufacturers", "sold_at"]
    available = [c for c in show_cols if c in df_latest.columns]
    st.dataframe(df_latest[available].rename(columns={"recall_date_readable":"recall_date"}))

# ---------------------------
# Map (approximate)
# ---------------------------
st.subheader("Geographic (approximate) — Recalls by Country")
# Small static mapping for demo (should use geocoding in production)
country_coords = {
    "United States": [37.0902, -95.7129],
    "USA": [37.0902, -95.7129],
    "Canada": [56.1304, -106.3468],
    "CAN": [56.1304, -106.3468],
    "Mexico": [23.6345, -102.5528],
}

if not df_country.empty:
    df_map = df_country.copy()
    df_map["lat"] = df_map["country"].map(lambda x: country_coords.get(x, [0,0])[0])
    df_map["lon"] = df_map["country"].map(lambda x: country_coords.get(x, [0,0])[1])
    df_map = df_map[df_map["lat"] != 0]  # only show known coords for clarity

    if not df_map.empty:
        st.pydeck_chart(pdk.Deck(
            map_style="mapbox://styles/mapbox/light-v9",
            initial_view_state=pdk.ViewState(latitude=37.0, longitude=-95.0, zoom=2),
            layers=[
                pdk.Layer(
                    "ScatterplotLayer",
                    data=df_map,
                    get_position='[lon, lat]',
                    get_radius="count * 5000",
                    get_fill_color='[200, 30, 0, 180]',
                    pickable=True
                )
            ],
        ))

st.caption("Note: Country geolocation is approximate and for demo purposes only. For production use, use a dedicated geo dataset or geocoding service.")

# ---------------------------
# Footer / tips
# ---------------------------
st.markdown("---")
st.markdown("**Tips**: If you see recall IDs instead of names in charts, the dashboard will automatically resolve them by fetching recall details. Cache helps reduce API pressure.")
