import streamlit as st
import pandas as pd
import feedparser
import requests
import folium
from streamlit_folium import st_folium
from shapely.geometry import shape, Point
from datetime import datetime, timedelta
import time

# === Load and Normalize Data ===
@st.cache_data
def load_data():
    df = pd.read_csv("cleaned_news_feeds.csv")
    df['country'] = df['country'].str.strip().str.lower()
    return df

@st.cache_data
def load_geojson():
    url = "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson"
    return requests.get(url).json()

news_df = load_data()
geojson = load_geojson()

def normalize_country(name):
    return name.strip().lower()

# Prepare feed counts by country
feed_counts = news_df.groupby('country').size().to_dict()

# Initialize session state
if 'selected_country' not in st.session_state:
    st.session_state.selected_country = None

# === Build Folium Map ===
m = folium.Map(location=[20, 0], zoom_start=2)

def style_function(feature):
    country_name = normalize_country(feature['properties']['name'])
    fill_color = "#ff0000" if country_name == st.session_state.selected_country else "#6495ED"
    opacity = 0.7 if feed_counts.get(country_name, 0) > 0 else 0.1
    return {
        'fillColor': fill_color,
        'color': 'black',
        'weight': 1,
        'fillOpacity': opacity,
    }

def highlight_function(feature):
    return {'weight': 3, 'color': 'yellow'}

folium.GeoJson(
    geojson,
    name="Countries",
    style_function=style_function,
    highlight_function=highlight_function,
    tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["Country:"])
).add_to(m)

# === Layout: 3 columns ===
st.markdown("<h1 style='margin-bottom: 10px;'>🌍 News Feed Map</h1>", unsafe_allow_html=True)
col1, col2, col3 = st.columns([1, 1, 1.2], gap="medium")

# === Map Column ===
with col1:
    st.markdown("### Map")
    map_data = st_folium(m, width=650, height=450)

# === Filters + Stats Column ===
with col2:
    st.markdown("### Filters")
    available_countries = sorted(news_df['country'].dropna().unique())
    selected_country = st.selectbox(
        "Select a country (or click on the map)",
        available_countries,
        index=available_countries.index(st.session_state.selected_country)
        if st.session_state.selected_country in available_countries else 0,
        key="selected_country_manual"
    )

    if selected_country != st.session_state.selected_country:
        st.session_state.selected_country = selected_country

    # === News Stats ===
    st.markdown("### 📊 News Statistics")
    country_media = news_df[news_df['country'] == st.session_state.selected_country]

    last_hour = datetime.utcnow() - timedelta(hours=1)
    today = datetime.utcnow().date()

    news_last_hour = 0
    news_today = 0
    source_counts = {}

    for _, row in country_media.iterrows():
        try:
            feed = feedparser.parse(row['newsfeed_url'])
            count_hour = 0
            count_day = 0

            for entry in feed.entries:
                if hasattr(entry, 'published_parsed'):
                    pub_time = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    if pub_time > last_hour:
                        count_hour += 1
                    if pub_time.date() == today:
                        count_day += 1

            news_last_hour += count_hour
            news_today += count_day
            source_counts[row['media_name']] = count_day
        except Exception:
            pass

    st.metric("🕐 News in Last Hour", news_last_hour)
    st.metric("📅 News Today", news_today)

    st.markdown("**🗞 News Per Source:**")
    for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        st.markdown(f"- **{source}**: {count} article(s) today")

# === News Feed Column ===
with col3:
    st.markdown("### News Feed")
    st.markdown("<div style='margin-top: -15px'></div>", unsafe_allow_html=True)

    feed_container = st.container()

# === Map click handling (AFTER rendering the map!) ===
if map_data and map_data.get("last_clicked"):
    point = Point(map_data["last_clicked"]['lng'], map_data["last_clicked"]['lat'])
    selected = None
    for feature in geojson['features']:
        geom = shape(feature['geometry'])
        if geom.contains(point):
            selected = normalize_country(feature['properties']['name'])
            break
    if selected:
        st.session_state.selected_country = selected

# === News Feed Rendering ===
with feed_container:
    country_media = news_df[news_df['country'] == st.session_state.selected_country]
    selected_media = st.selectbox(
        "Select a Media Outlet", ["All"] + sorted(country_media['media_name'].dropna().unique())
    )

    if selected_media != "All":
        feed_rows = country_media[country_media['media_name'] == selected_media]
    else:
        feed_rows = country_media

    if feed_rows.empty:
        st.warning("No feeds found for the selected country or media.")
    else:
        for _, row in feed_rows.iterrows():
            try:
                feed = feedparser.parse(row['newsfeed_url'])
                if feed.entries:
                    st.subheader(f"📰 {row['media_name']}")
                    st.caption(f"URL: {row['newsfeed_url']}")
                    for entry in feed.entries[:5]:
                        st.markdown(f"- [{entry.title}]({entry.link})")
            except Exception as e:
                st.error(f"Error parsing feed: {e}")
