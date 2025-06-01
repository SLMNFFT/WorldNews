import streamlit as st
import pandas as pd
import feedparser
import requests
import folium
from streamlit_folium import st_folium
from shapely.geometry import shape, Point
from datetime import datetime, timedelta
import time
from urllib.parse import urlparse
from gtts import gTTS
import os
import base64

# ==== Page Setup ====
st.set_page_config(page_title="NewsMap", layout="wide", page_icon="🎧")

# ==== Load Data ====
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

feed_counts = news_df.groupby('country').size().to_dict()

def get_country_centroid(country_name):
    country_name = normalize_country(country_name)
    for feature in geojson['features']:
        name = normalize_country(feature['properties']['name'])
        if name == country_name:
            geom = shape(feature['geometry'])
            centroid = geom.centroid
            return [centroid.y, centroid.x]
    return [20, 0]  # Fallback center

# ==== Session State ====
if 'selected_country' not in st.session_state:
    st.session_state.selected_country = "germany"

# ==== Layout ====
st.markdown("<h1 style='margin-bottom: 10px;'>🌍 PRESSEBOT - News Cockpit </h1>", unsafe_allow_html=True)

col1, col2, col3 = st.columns([3, 0.2, 2], gap="medium")

with col1:
    available_countries = sorted(news_df['country'].dropna().unique())

    selected_country_dropdown = st.selectbox(
        "Select a country",
        available_countries,
        index=available_countries.index(st.session_state.selected_country) if st.session_state.selected_country in available_countries else 0,
        key="country_select"
    )

    if selected_country_dropdown != st.session_state.selected_country:
        st.session_state.selected_country = selected_country_dropdown

    center_coords = get_country_centroid(st.session_state.selected_country)
    m = folium.Map(location=center_coords, zoom_start=4)

    def style_function(feature):
        country = normalize_country(feature['properties']['name'])
        fill_color = "#ff0000" if country == st.session_state.selected_country else "#6495ED"
        opacity = 0.7 if feed_counts.get(country, 0) > 0 else 0.1
        return {'fillColor': fill_color, 'color': 'black', 'weight': 1, 'fillOpacity': opacity}

    folium.GeoJson(
        geojson,
        name="Countries",
        style_function=style_function,
        highlight_function=lambda f: {'weight': 3, 'color': 'yellow'},
        tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["Country:"])
    ).add_to(m)

    map_data = st_folium(m, width=700, height=450)

    if map_data and map_data.get("last_clicked"):
        point = Point(map_data["last_clicked"]['lng'], map_data["last_clicked"]['lat'])
        for feature in geojson['features']:
            if shape(feature['geometry']).contains(point):
                clicked_country = normalize_country(feature['properties']['name'])
                if clicked_country != st.session_state.selected_country:
                    st.session_state.selected_country = clicked_country

    st.markdown("### 📊 News Statistics")
    media_df = news_df[news_df['country'] == st.session_state.selected_country]
    last_hour = datetime.utcnow() - timedelta(hours=1)
    today = datetime.utcnow().date()

    news_hour, news_today = 0, 0
    stats = []

    for _, row in media_df.iterrows():
        try:
            feed = feedparser.parse(row['newsfeed_url'])
            hour_count = sum(1 for entry in feed.entries if hasattr(entry, 'published_parsed') and datetime.fromtimestamp(time.mktime(entry.published_parsed)) > last_hour)
            today_count = sum(1 for entry in feed.entries if hasattr(entry, 'published_parsed') and datetime.fromtimestamp(time.mktime(entry.published_parsed)).date() == today)
            news_hour += hour_count
            news_today += today_count

            parsed_url = urlparse(row['newsfeed_url'])
            favicon_url = f"{parsed_url.scheme}://{parsed_url.netloc}/favicon.ico"

            stats.append({
                "media_name": row['media_name'],
                "today_count": today_count,
                "favicon_url": favicon_url
            })
        except Exception:
            pass

    col_s1, col_s2 = st.columns(2)
    col_s1.metric("🕐 Last Hour", news_hour)
    col_s2.metric("📅 Today", news_today)

    st.markdown("**🗞 Per Source:**")
    cols_per_row = 3
    for i in range(0, len(stats), cols_per_row):
        cols = st.columns(cols_per_row)
        for idx, stat in enumerate(stats[i:i+cols_per_row]):
            with cols[idx]:
                st.image(stat['favicon_url'], width=32)
                st.markdown(f"**{stat['media_name']}**")
                st.markdown(f"{stat['today_count']} today")

with col2:
    st.write("")

with col3:
    st.markdown("---")
    st.markdown("### 📰 News Feed")

    selected_media = st.selectbox("Choose Media Outlet", ["All"] + sorted(media_df['media_name'].dropna().unique()))
    feed_rows = media_df[media_df['media_name'] == selected_media] if selected_media != "All" else media_df

    all_texts = []

    for _, row in feed_rows.iterrows():
        try:
            feed = feedparser.parse(row['newsfeed_url'])
            if feed.entries:
                st.subheader(f"📰 {row['media_name']}")
                st.caption(f"URL: {row['newsfeed_url']}")
                text_block = " ".join(entry.title.replace("`", "'").replace("\n", " ") for entry in feed.entries[:5])
                all_texts.append(f"{row['media_name']}: {text_block}")

                for entry in feed.entries[:5]:
                    st.markdown(f"- [{entry.title}]({entry.link})")
        except Exception as e:
            st.error(f"Error parsing feed: {e}")

    # === 🔊 Global Audio Controls ===
    st.markdown("---")
    st.markdown("### 🔊 Global Controls")

    if all_texts:
        full_text = " ".join(all_texts).replace("`", "'")
        audio_file_path = "news_summary.mp3"

        if st.button("▶️ Generate & Play Audio"):
            try:
                tts = gTTS(full_text)
                tts.save(audio_file_path)
                audio_bytes = open(audio_file_path, "rb").read()
                st.audio(audio_bytes, format="audio/mp3")
            except Exception as e:
                st.error(f"Failed to generate audio: {e}")

        if os.path.exists(audio_file_path):
            with open(audio_file_path, "rb") as file:
                b64 = base64.b64encode(file.read()).decode()
                href = f'<a href="data:audio/mp3;base64,{b64}" download="news_summary.mp3">⬇️ Download Audio</a>'
                st.markdown(href, unsafe_allow_html=True)
