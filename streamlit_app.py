import streamlit as st
import pandas as pd
import feedparser
import requests
import folium
from streamlit_folium import st_folium
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

# Prepare feed counts by country
feed_counts = news_df.groupby('country').size().to_dict()

# Initialize session state for selected country
if 'selected_country' not in st.session_state:
    st.session_state.selected_country = None

# === Build Folium Map ===
m = folium.Map(location=[20, 0], zoom_start=2)

# Function to style countries
def style_function(feature):
    country_name = normalize_country(feature['properties']['name'])
    fill_color = "#ff0000" if country_name == st.session_state.selected_country else "#6495ED"  # red selected, cornflower blue otherwise
    opacity = 0.7 if feed_counts.get(country_name, 0) > 0 else 0.1
    return {
        'fillColor': fill_color,
        'color': 'black',
        'weight': 1,
        'fillOpacity': opacity,
    }

# Function to highlight on hover
def highlight_function(feature):
    return {'weight':3, 'color':'yellow'}

# Add GeoJSON layer with tooltips and click handling
geojson_layer = folium.GeoJson(
    geojson,
    name="Countries",
    style_function=style_function,
    highlight_function=highlight_function,
    tooltip=folium.GeoJsonTooltip(
        fields=["name"],
        aliases=["Country:"],
        localize=True
    )
).add_to(m)

# Add click handler to update selected country in Streamlit
click_script = """
function onMapClick(e) {
    let layer = e.target;
    let props = layer.feature.properties;
    let countryName = props.name.toLowerCase();
    // Send country name back to Streamlit
    window.parent.postMessage({isStreamlitMessage:true, type:'COUNTRY_CLICKED', country: countryName}, "*");
}
"""

# Attach click event to each country feature
for feature in geojson_layer.data['features']:
    # Add onEachFeature JS function to add click listener
    feature['onEachFeature'] = """
    function(feature, layer) {
        layer.on({
            click: function(e) {
                var countryName = feature.properties.name.toLowerCase();
                window.parent.postMessage({isStreamlitMessage:true, type:'COUNTRY_CLICKED', country: countryName}, "*");
            }
        });
    }
    """

# Because folium does not support direct JS in GeoJson features easily,
# We will add a simpler approach using st_folium and catch clicks

map_data = st_folium(m, width=700, height=450)

# Process clicks returned from st_folium
if map_data and map_data.get("last_clicked"):
    latlng = map_data["last_clicked"]
    # Find which country polygon contains this lat/lng
    from shapely.geometry import Point

    point = Point(latlng['lng'], latlng['lat'])
    selected = None
    for feature in geojson['features']:
        geom = shape(feature['geometry'])
        if geom.contains(point):
            selected = normalize_country(feature['properties']['name'])
            break
    if selected:
        st.session_state.selected_country = selected

# === UI ===
st.title("🌍 News Feed Map")

# Select box fallback to select country manually
available_countries = sorted(news_df['country'].dropna().unique())
selected_country = st.selectbox("Select a country (or click on the map)", available_countries,
                                index=available_countries.index(st.session_state.selected_country)
                                      if st.session_state.selected_country in available_countries else 0,
                                key="selected_country_manual")

# Sync manual selection to session state
if selected_country != st.session_state.selected_country:
    st.session_state.selected_country = selected_country

# Show feeds for the selected country
country_media = news_df[news_df['country'] == st.session_state.selected_country]
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
