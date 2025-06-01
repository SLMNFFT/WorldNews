import streamlit as st
import pandas as pd
import feedparser
import requests
import folium
from streamlit_folium import st_folium
from shapely.geometry import shape, Point
from datetime import datetime, timedelta
import time

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

# ==== Session State ====
if 'selected_country' not in st.session_state:
    st.session_state.selected_country = "germany"

# ==== Layout ====
st.markdown("<h1 style='margin-bottom: 10px;'>🌍 News Feed Map</h1>", unsafe_allow_html=True)
map_col, news_col = st.columns([2, 1.5], gap="medium")

# ==== Sidebar Voice Controls ====
with st.sidebar:
    st.header("🔊 Voice Controls")
    language = st.selectbox("TTS Language", ["en-US", "en-GB", "de-DE", "fr-FR", "es-ES", "it-IT", "ja-JP", "zh-CN"], index=2)
    volume = st.slider("Volume", 0.0, 1.0, 1.0, 0.1)
    rate = st.slider("Speed", 0.1, 2.0, 1.0, 0.1)

# ==== Column 1: Country Dropdown + Map ====
with map_col:
    available_countries = sorted(news_df['country'].dropna().unique())
    selected_country = st.selectbox(
        "Select a country", 
        available_countries,
        index=available_countries.index(st.session_state.selected_country) if st.session_state.selected_country in available_countries else 0
    )
    if selected_country != st.session_state.selected_country:
        st.session_state.selected_country = selected_country

    m = folium.Map(location=[20, 0], zoom_start=2)

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

    map_data = st_folium(m, width=1300, height=450)

    # Map click logic
    if map_data and map_data.get("last_clicked"):
        point = Point(map_data["last_clicked"]['lng'], map_data["last_clicked"]['lat'])
        for feature in geojson['features']:
            if shape(feature['geometry']).contains(point):
                st.session_state.selected_country = normalize_country(feature['properties']['name'])
                break

# ==== Column 2: Stats + News ====
media_df = news_df[news_df['country'] == st.session_state.selected_country]
last_hour = datetime.utcnow() - timedelta(hours=1)
today = datetime.utcnow().date()
news_hour, news_today, source_counts = 0, 0, {}

with news_col:
    # --- News Statistics ---
    st.markdown("### 📊 News Statistics")
    for _, row in media_df.iterrows():
        try:
            feed = feedparser.parse(row['newsfeed_url'])
            hour_count = sum(1 for entry in feed.entries if hasattr(entry, 'published_parsed') and datetime.fromtimestamp(time.mktime(entry.published_parsed)) > last_hour)
            today_count = sum(1 for entry in feed.entries if hasattr(entry, 'published_parsed') and datetime.fromtimestamp(time.mktime(entry.published_parsed)).date() == today)
            news_hour += hour_count
            news_today += today_count
            source_counts[row['media_name']] = today_count
        except:
            pass

    st.metric("🕐 Last Hour", news_hour)
    st.metric("📅 Today", news_today)
    st.markdown("**🗞 Per Source:**")
    for source, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        st.markdown(f"- **{source}**: {count} today")

    # --- News Feed ---
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

                btn_id = f"read_btn_{row['media_name'].replace(' ', '_')}"
                st.markdown(f'<button id="{btn_id}">🔊 Read Aloud</button>', unsafe_allow_html=True)
                st.components.v1.html(f"""
                    <script>
                        const btn = document.getElementById('{btn_id}');
                        btn.onclick = () => {{
                            const u = new SpeechSynthesisUtterance(`{text_block}`);
                            u.lang = '{language}';
                            u.volume = {volume};
                            u.rate = {rate};
                            window.speechSynthesis.cancel();
                            window.speechSynthesis.speak(u);
                        }};
                    </script>
                """, height=0)
        except Exception as e:
            st.error(f"Error parsing feed: {e}")

    # --- Global TTS ---
    st.markdown("---")
    st.markdown("### 🔊 Global Controls")
    st.markdown("""
        <button id="global_play">▶️ Play</button>
        <button id="global_pause">⏸ Pause</button>
        <button id="global_resume">▶ Resume</button>
        <button id="global_stop">⏹ Stop</button>
    """, unsafe_allow_html=True)

    full_text = " ".join(all_texts).replace("`", "'")
    st.components.v1.html(f"""
        <script>
            const globalUtter = new SpeechSynthesisUtterance(`{full_text}`);
            globalUtter.lang = '{language}';
            globalUtter.volume = {volume};
            globalUtter.rate = {rate};
            let synth = window.speechSynthesis;

            document.getElementById("global_play").onclick = () => {{
                synth.cancel();
                synth.speak(globalUtter);
            }};
            document.getElementById("global_pause").onclick = () => synth.pause();
            document.getElementById("global_resume").onclick = () => synth.resume();
            document.getElementById("global_stop").onclick = () => synth.cancel();
        </script>
    """, height=0)
