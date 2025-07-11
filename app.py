# app.py - STAGE 1: DIAGNOSTIC NEWS FETCHER

import streamlit as st
import requests
import pandas as pd
from io import StringIO
import time

# --- List of news sources to try in order ---
# We will try these one by one until one works.
NEWS_SOURCES = {
    "LiveMint": "https://www.livemint.com/rss/topnews",
    "Reuters (World News)": "http://feeds.reuters.com/reuters/INtopNews", # A very reliable international source
    "Google News (India)": "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"
}

st.set_page_config(page_title="App Diagnosis", layout="wide")
st.title("🕵️‍♂️ App Diagnosis: Testing News Sources")
st.info("This test will try to fetch news from multiple sources to find one that is not blocked by the cloud server.")

@st.cache_data(ttl=600) # Cache for 10 minutes during testing
def find_working_news_source():
    """Tries to fetch news from a list of URLs and returns the first one that works."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    for name, url in NEWS_SOURCES.items():
        try:
            st.write(f"---")
            st.write(f"Attempting to fetch from **{name}**...")
            st.code(url)

            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status() # Raise an error for bad responses (like 502)
            
            # If we reach here, the request was successful
            st.success(f"✅ SUCCESS! Successfully connected to {name}.")
            
            # Now, let's try to parse it to be sure
            xml_content = StringIO(response.text)
            df = pd.read_xml(xml_content)
            
            if 'title' in df.columns:
                st.success(f"✅ Data from {name} is valid and contains headlines.")
                return df, name # Return the working dataframe and the name of the source
            else:
                st.error(f"Connected to {name}, but the data format is incorrect. Missing 'title' column.")

        except Exception as e:
            st.error(f"❌ FAILED to fetch or parse from {name}. Error: {e}")
            time.sleep(1) # Wait a second before trying the next one

    # This part only runs if the loop finishes without returning
    st.error("---")
    st.error("🚨 CRITICAL: All news sources failed. The server environment may have strict network restrictions.")
    return None, None


# --- Main App Logic ---
df_news, source_name = find_working_news_source()

st.header("Results")
if df_news is not None:
    st.success(f"Displaying news from the working source: **{source_name}**")
    st.dataframe(df_news.head(10), use_container_width=True, hide_index=True)
else:
    st.error("Could not fetch news from any of the tested sources.")
