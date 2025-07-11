# app.py

import streamlit as st
import pandas as pd
from textblob import TextBlob
import requests
import logging
from io import StringIO

# --- CONFIGURATION (using Streamlit Secrets) ---
# This part remains, but Telegram alerts will be disabled since there are no stocks to suggest.
try:
    TELEGRAM_TOKEN = st.secrets["telegram"]["token"]
    TELEGRAM_CHAT_ID = st.secrets["telegram"]["chat_id"]
except (KeyError, FileNotFoundError):
    st.info("Telegram credentials not found. This is okay for now.")
    TELEGRAM_TOKEN = None
    TELEGRAM_CHAT_ID = None

# --- CONSTANTS ---
NEWS_RSS_URL = "https://www.moneycontrol.com/rss/business.xml"
# We don't need the stock list file for this version.
# STOCK_LIST_CSV = "nifty500_stocks.csv"

# --- Keywords mapping for sector identification ---
SECTOR_KEYWORDS = {
    'AUTOMOBILE': ['auto', 'maruti', 'mahindra', 'tata motors', 'hero', 'bajaj', 'ev'],
    'PHARMA': ['pharma', 'health', 'cipla', 'sun pharma', 'lupin', 'dr reddy', 'healthcare'],
    'TECH': ['it', 'tech', 'tcs', 'infosys', 'wipro', 'hcl', 'software'],
    'BANKING & FINANCE': ['bank', 'hdfc', 'icici', 'sbi', 'axis', 'finance', 'rbi', 'nbfc'],
    'OIL & GAS': ['oil', 'gas', 'ongc', 'reliance', 'bpcl', 'crude', 'energy'],
    'METALS': ['metal', 'steel', 'tata steel', 'jsw', 'hindalco', 'coal', 'mining'],
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ========= DATA LOADING & ANALYSIS FUNCTIONS =========

@st.cache_data(ttl=3600) # Cache news for 1 hour
def fetch_news_from_rss(url):
    """Fetches news headlines from an RSS feed robustly."""
    try:
        logging.info("Fetching fresh news from RSS feed...")
        # Use requests to act like a browser, which is more reliable
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # Raise an error for bad responses

        # Use StringIO to read the text content as if it were a file
        xml_content = StringIO(response.text)
        df = pd.read_xml(xml_content)
        
        if 'title' in df.columns and 'link' in df.columns:
            return df[['title', 'link']].head(15)
        else:
            st.error("RSS feed is valid but is missing 'title' or 'link' columns.")
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"Failed to fetch or parse news feed: {e}")
        return pd.DataFrame()

def analyze_sentiment(text):
    """Analyzes sentiment and returns a label and a score."""
    analysis = TextBlob(text)
    polarity = analysis.sentiment.polarity
    label = 'POSITIVE' if polarity > 0.1 else 'NEGATIVE' if polarity < -0.1 else 'NEUTRAL'
    return label, polarity

def map_headline_to_sector(headline):
    """Identifies a sector from a headline using keywords."""
    headline_lower = headline.lower()
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(keyword in headline_lower for keyword in keywords):
            return sector
    return "MISCELLANEOUS"

# --- STOCK ANALYSIS DISABLED AS PER REQUEST ---
# The function below is kept as a placeholder for when you want to re-enable it.
def load_nse_stocks():
    """This function is currently disabled."""
    # When you are ready, you can add back the pd.read_csv logic here.
    # For now, it returns an empty dictionary to prevent errors.
    return {}

# ========= STREAMLIT UI =========

st.set_page_config(page_title="AI News Advisor", layout="wide")
st.title("📈 AI Market News Advisor")
st.markdown("This version focuses on fetching live business news, analyzing sentiment, and identifying affected sectors.")

st.sidebar.header("Status")
st.sidebar.success("News Analysis: **Active**")
st.sidebar.warning("Stock Suggestions: **Disabled**")
st.sidebar.info("When you have the stock data file ready, we can re-enable the suggestion feature.")

# --- Main App Logic ---
news_df = fetch_news_from_rss(NEWS_RSS_URL)

st.header("📰 Latest Business Headlines")
if news_df.empty:
    st.warning("Could not display news. Please check the error messages at the top of the page.")
else:
    # Display the raw news headlines in a clean table
    st.dataframe(news_df, use_container_width=True, hide_index=True)

st.header("💬 Sentiment Analysis & Sector Mapping")
if news_df.empty:
    st.warning("Analysis cannot run because no news was fetched.")
else:
    # Loop through each headline and display its analysis
    for index, row in news_df.iterrows():
        headline = row['title']
        sentiment, score = analyze_sentiment(headline)
        
        # We only care about strongly positive or negative news
        if sentiment != 'NEUTRAL':
            mapped_sector = map_headline_to_sector(headline)
            
            sentiment_emoji = "🟢" if sentiment == "POSITIVE" else "🔴"
            
            with st.container(border=True):
                st.markdown(f"**{sentiment_emoji} [{sentiment}]** {headline}")
                st.markdown(f"> **Sector:** `{mapped_sector}` | **Sentiment Score:** `{score:.2f}`")
                st.info("💡 Stock analysis is disabled. No recommendations will be shown.")
