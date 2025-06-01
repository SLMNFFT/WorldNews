import streamlit as st
import pandas as pd
import feedparser
import pydeck as pdk
import requests
from shapely.geometry import shape

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

# === Feed Count and Geo Layer Preprocessing ===
feed_counts = news_df.groupby('country').size().to_dict()

# === Handle Selected Country ===
if "selected_country" not in st.session_state:
    st.session_state.selected_country = ""

# === UI Dropdown (fallback for selection) ===
available_countries = sorted(news_df['country'].dropna().unique())
selected_country = st.selectbox(
    "Select a country",
    available_countries,
    index=available_countries.index(st.session_state.selected_country)
    if st.session_state.selected_country in available_countries else 0,
    key="selected_country"
)

# === Update GeoJSON fill color based on selection ===
for feature in geojson['features']:
    country_name_raw = feature['properties'].get('NAME', '')
    country_name = normalize_country(country_name_raw)
    is_selected = country_name == st.session_state.selected_country
    feature['properties']['fill_color'] = [255, 0, 0, 180] if is_selected else [100, 100, 200, 100]
    feature['properties']['tooltip_name'] = country_name_raw

# === Compute Centroids for Text Labels ===
def compute_centroids(geojson):
    centroids = []
    for feature in geojson["features"]:
        name = normalize_country(feature["properties"].get("NAME", ""))
        geom = shape(feature["geometry"])
        count = feed_counts.get(name, 0)
        if count > 0:
            centroids.append({
                "position": [geom.centroid.x, geom.centroid.y],
                "text": f"{name.title()} - {count}"
            })
    return centroids

centroids = compute_centroids(geojson)

# === Pydeck Layers ===
geo_layer = pdk.Layer(
    "GeoJsonLayer",
    data=geojson,
    pickable=True,
    stroked=True,
    filled=True,
    get_fill_color="properties.fill_color",
    get_line_color=[255, 255, 255],
    auto_highlight=True
)

text_layer = pdk.Layer(
    "TextLayer",
    data=centroids,
    get_position="position",
    get_text="text",
    get_size=16,
    get_color=[0, 0, 0],
    size_units="pixels",
    get_text_anchor="middle",
    get_alignment_baseline="center"
)

view_state = pdk.ViewState(latitude=20, longitude=0, zoom=1.2)

deck = pdk.Deck(
    layers=[geo_layer, text_layer],
    initial_view_state=view_state,
    tooltip={"text": "{tooltip_name}"}
)

# === Show Map ===
st.pydeck_chart(deck)

# === Display Feeds Below Map ===
country_media = news_df[news_df['country'] == selected_country]
media_names = sorted(country_media['media_name'].dropna().unique())
selected_media = st.selectbox("Select a Media Outlet", ["All"] + media_names)

if selected_media != "All":
    feed_rows = country_media[country_media['media_name'] == selected_media]
else:
    feed_rows = country_media

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
