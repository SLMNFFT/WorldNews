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
from timezonefinder import TimezoneFinder
import pytz

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
    return [20, 0]  # fallback

# ==== Session State Initialization ====
available_countries = sorted(news_df['country'].dropna().unique())

if 'selected_country' not in st.session_state:
    st.session_state.selected_country = "germany"

if 'country_select' not in st.session_state:
    st.session_state.country_select = st.session_state.selected_country

def on_country_change():
    st.session_state.selected_country = st.session_state.country_select

# ==== Local Time & Weather (Header) ====

st.markdown("<h1 style='margin-bottom: 10px;'>🌍 PRESSEBOT - News Cockpit</h1>", unsafe_allow_html=True)

center_coords = get_country_centroid(st.session_state.selected_country)
lat, lon = center_coords

def get_local_time(lat, lon):
    tf = TimezoneFinder()
    try:
        tz_str = tf.timezone_at(lat=lat, lng=lon)
        if not tz_str:
            return "N/A"
        tz = pytz.timezone(tz_str)
        local_time = datetime.now(tz)
        return local_time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "N/A"

def get_weather(lat, lon):
    try:
        url = f"https://wttr.in/{lat},{lon}?format=j1"
        response = requests.get(url, timeout=5)
        data = response.json()
        current = data['current_condition'][0]
        weather_state = current['weatherDesc'][0]['value']
        temp_c = current['temp_C']
        humidity = current['humidity']
        wind_kmph = current['windspeedKmph']
        return f"{weather_state}, {temp_c}°C, Humidity: {humidity}%, Wind: {wind_kmph} km/h"
    except Exception as e:
        print(f"Weather fetch error: {e}")
        return None

local_time = get_local_time(lat, lon)
weather_info = get_weather(lat, lon)

# Collect all news texts for TTS (you can keep this here for audio setup)
media_df = news_df[news_df['country'] == st.session_state.selected_country]
all_texts = []
for _, row in media_df.iterrows():
    try:
        feed = feedparser.parse(row['newsfeed_url'])
        if feed.entries:
            text_block = " ".join(entry.title.replace("`", "'").replace("\n", " ") for entry in feed.entries[:5])
            all_texts.append(f"{row['media_name']}: {text_block}")
    except Exception:
        pass

# === HEADER WITH TWO COLUMNS ===
header_col1, header_col2 = st.columns([2, 3])

with header_col1:
    st.markdown(
        f"""
        <div style='text-align:left; margin-bottom: 15px;'>
            <h3>⏰ Local Time & 🌤 Weather</h3>
            <p><strong>Location:</strong> {st.session_state.selected_country.title()}</p>
            <p style='font-size:28px; font-weight:bold; margin: 0;'>{local_time}</p>
            <p><strong>Weather:</strong> {weather_info if weather_info else 'Unable to retrieve weather data'}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

with header_col2:
    st.markdown(
    """
    <div style='text-align:left; margin-bottom: 15px;'>
        <h3>🔊 Audio Setup</h3>
    </div>
    """,
    unsafe_allow_html=True
)


    languages = {
        'English (US)': 'en',
        'English (UK)': 'en-uk',
        'German': 'de',
        'French': 'fr',
        'Spanish': 'es',
        'Italian': 'it',
        'Portuguese': 'pt',
        'Russian': 'ru',
        'Chinese (Mandarin)': 'zh-CN',
        'Arabic': 'ar'
    }
    selected_lang = st.selectbox("Select Language", list(languages.keys()), index=0, key="audio_lang")
    tts_speed = st.slider("Speech Speed (0.5 = slow, 2.0 = fast)", 0.5, 2.0, 1.0, 0.1, key="audio_speed")

    if st.button("Play Combined News Summary Audio", key="play_audio"):
        combined_text = "\n".join(all_texts)
        if combined_text.strip():
            # gTTS does not support speech speed adjustment directly; ignoring speed here.
            tts = gTTS(text=combined_text, lang=languages[selected_lang].split('-')[0], slow=False)
            audio_file = "news_summary.mp3"
            tts.save(audio_file)
            audio_bytes = open(audio_file, "rb").read()
            st.audio(audio_bytes, format="audio/mp3")
            os.remove(audio_file)
        else:
            st.warning("No text to read.")

# ==== Main layout ====
col1, col2, col3 = st.columns([3, 0.01, 2], gap="medium")

with col1:
    # === Country Dropdown ===
    selected_country_dropdown = st.selectbox(
        "Select a country",
        available_countries,
        index=available_countries.index(st.session_state.country_select),
        key="country_select",
        on_change=on_country_change
    )

    # === Map ===
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
                if clicked_country in available_countries and clicked_country != st.session_state.selected_country:
                    st.session_state.selected_country = clicked_country
                    st.session_state.country_select = clicked_country
                    st.experimental_rerun()

    # === News Statistics ===
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
    st.empty()

with col3:
    st.markdown("---")
    st.markdown("### 📰 News Feed")

    selected_media = st.selectbox("Choose Media Outlet", ["All"] + sorted(media_df['media_name'].dropna().unique()))
    feed_rows = media_df[media_df['media_name'] == selected_media] if selected_media != "All" else media_df

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
