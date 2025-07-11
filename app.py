# app.py - FINAL WORKING VERSION

import streamlit as st
import pandas as pd
from textblob import TextBlob
import yfinance as yf
import requests
import logging
from io import StringIO
import time

# --- CONFIGURATION ---
try:
    TELEGRAM_TOKEN = st.secrets["telegram"]["token"]
    TELEGRAM_CHAT_ID = st.secrets["telegram"]["chat_id"]
except (KeyError, FileNotFoundError):
    st.info("Telegram credentials not found. Alerts will be disabled.")
    TELEGRAM_TOKEN = None
    TELEGRAM_CHAT_ID = None

# --- CONSTANTS ---
# <<< --- USING THE CONFIRMED WORKING NEWS SOURCE --- >>>
NEWS_RSS_URL = "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"
STOCK_LIST_CSV = "nifty500_stocks.csv"

# Keywords to map news to sectors.
SECTOR_KEYWORDS = {
    'AUTOMOBILE & AUTO COMPONENTS': ['auto', 'maruti', 'mahindra', 'tata motors', 'hero', 'bajaj', 'ev', 'automotive'],
    'PHARMA & HEALTHCARE': ['pharma', 'health', 'cipla', 'sun pharma', 'lupin', 'dr reddy', 'healthcare', 'vaccine'],
    'IT - SOFTWARE': ['it', 'tech', 'tcs', 'infosys', 'wipro', 'hcl', 'software', 'fintech'],
    'FINANCIAL SERVICES': ['bank', 'hdfc', 'icici', 'sbi', 'axis', 'finance', 'rbi', 'nbfc', 'insurance'],
    'OIL GAS & FUELS': ['oil', 'gas', 'ongc', 'reliance', 'bpcl', 'crude', 'energy', 'fuel'],
    'METALS & MINING': ['metal', 'steel', 'tata steel', 'jsw', 'hindalco', 'coal', 'mining'],
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ========= DATA LOADING & ANALYSIS FUNCTIONS =========

@st.cache_data(ttl=1800) # Cache news for 30 minutes
def fetch_news_from_rss(url):
    """Fetches news from our confirmed working source."""
    try:
        logging.info(f"Fetching news from Google News RSS...")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        xml_content = StringIO(response.text)
        df = pd.read_xml(xml_content)
        
        if 'title' in df.columns and 'link' in df.columns:
            st.success("✅ Successfully fetched latest news from Google News.")
            return df[['title', 'link']].head(20) # Get a few more headlines
    except Exception as e:
        st.error(f"Failed to fetch or parse Google News feed: {e}")
    return pd.DataFrame()

@st.cache_data
def load_nse_stocks():
    """Loads NSE stock list from the correct constituents CSV file."""
    try:
        df = pd.read_csv(STOCK_LIST_CSV)
        stock_column, industry_column = 'Symbol', 'Industry'

        if stock_column not in df.columns or industry_column not in df.columns:
            st.error(f"CRITICAL ERROR: Your CSV file is missing '{stock_column}' or '{industry_column}'.")
            st.info(f"👉 **FIX:** Ensure you have the correct NIFTY 500 CONSTITUENTS list from the NSE page.")
            st.code(f"Columns found in your file: {list(df.columns)}")
            return {}
        
        df[industry_column] = df[industry_column].str.upper().str.strip()
        sector_stocks = df.groupby(industry_column)[stock_column].apply(list).to_dict()
        st.success("✅ Successfully loaded and parsed the NIFTY 500 stock list.")
        return sector_stocks
        
    except FileNotFoundError:
        st.error(f"CRITICAL ERROR: Stock list file `{STOCK_LIST_CSV}` not found. Please ensure it's uploaded to GitHub.")
        return {}
    except Exception as e:
        st.error(f"An unexpected error occurred while loading the stock CSV: {e}")
        return {}

# --- All helper functions below are correct ---
def analyze_sentiment(text):
    # Remove the source name from Google News headlines (e.g., " - Times of India")
    text_cleaned = text.rsplit(' - ', 1)[0]
    analysis = TextBlob(text_cleaned)
    return 'POSITIVE' if analysis.sentiment.polarity > 0.1 else 'NEGATIVE' if analysis.sentiment.polarity < -0.1 else 'NEUTRAL', analysis.sentiment.polarity

def map_headline_to_sector(headline):
    headline_lower = headline.lower()
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(keyword in headline_lower for keyword in keywords): return sector.upper()
    return None

@st.cache_data(ttl=86400)
def analyze_stock_performance(symbol):
    try:
        stock_data = yf.download(f"{symbol}.NS", period="6mo", progress=False)
        if stock_data.empty: return None
        return {'symbol': symbol, 'avg_return': stock_data['Close'].pct_change().mean()}
    except Exception: return None
        
def format_telegram_message(headline_info, recommendations):
    headline, sentiment, score, sector = headline_info.values()
    message = f"🚨 *AI Market Advisor Alert*\n\n📰 *Headline:* {headline}\n📊 *Sentiment:* {sentiment} (Score: {score:.2f})\n🏭 *Affected Sector:* {sector}\n\n"
    message += "📈 *Top BUY Recommendations:*\n" if sentiment == 'POSITIVE' else "📉 *Top AVOID Recommendations:*\n"
    if not recommendations: message += "_No stocks met the filter criteria._"
    else:
        for stock in recommendations: message += f"  - *{stock['symbol']}* (Avg Daily Return: {stock['avg_return'] * 100:.3f}%)\n"
    return message

def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: st.warning("Telegram is not configured."); return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200: st.toast("✅ Alert sent to Telegram!")
        else: st.error(f"Failed to send Telegram message: {response.text}")
    except Exception as e: st.error(f"Exception while sending Telegram message: {e}")

# ========= STREAMLIT UI =========
st.set_page_config(page_title="AI Market Advisor", layout="wide")
st.title("📈 AI Market Advisor – News & Stock Picks")
st.sidebar.header("Controls")
if st.sidebar.button("🔄 Clear Cache and Rerun"): st.cache_data.clear(); st.rerun()
st.sidebar.warning("**Disclaimer:** This is for educational purposes. Not financial advice.")

# --- Load Data and Show Status in Sidebar ---
with st.sidebar:
    st.header("Data Status")
    sector_stocks_map = load_nse_stocks()
    news_df = fetch_news_from_rss(NEWS_RSS_URL)

# --- Main Page Layout ---
st.header("📰 Latest Business Headlines from Google News")
if news_df.empty: st.warning("Could not display news. Please check for error messages.")
else: st.dataframe(news_df, use_container_width=True, hide_index=True)

st.header("💬 Sentiment Analysis & Stock Suggestions")
if news_df.empty or not sector_stocks_map:
    st.warning("Analysis cannot run until all data loading issues are resolved.")
else:
    for index, row in news_df.iterrows():
        headline, (sentiment, score) = row['title'], analyze_sentiment(row['title'])
        if sentiment != 'NEUTRAL':
            mapped_sector = map_headline_to_sector(headline)
            if mapped_sector:
                with st.expander(f"{'🟢' if sentiment == 'POSITIVE' else '🔴'} [{sentiment}] {headline.rsplit(' - ', 1)[0]}"):
                    st.markdown(f"**Sector:** `{mapped_sector}` | **Sentiment Score:** `{score:.2f}`")
                    stocks_in_sector = sector_stocks_map.get(mapped_sector, [])
                    if not stocks_in_sector:
                        st.warning(f"No stocks found for '{mapped_sector}'.")
                        continue
                    with st.spinner(f"Analyzing {len(stocks_in_sector)} stocks..."):
                        valid_stocks = [s for s in [analyze_stock_performance(s) for s in stocks_in_sector] if s is not None]
                    recommendations = sorted([s for s in valid_stocks if (s['avg_return'] > 0.001 if sentiment == 'POSITIVE' else s['avg_return'] < -0.001)], key=lambda x: x['avg_return'], reverse=(sentiment == 'POSITIVE'))
                    if recommendations:
                        st.write("**Top Recommendations:**")
                        rec_df = pd.DataFrame(recommendations[:3])
                        rec_df['avg_return'] = rec_df['avg_return'].map('{:.3%}'.format)
                        st.dataframe(rec_df, use_container_width=True, hide_index=True)
                        if st.button("Send Alert", key=f"send_{index}"):
                            send_telegram_message(format_telegram_message({'title': headline.rsplit(' - ', 1)[0], 'sentiment': sentiment, 'score': score, 'sector': mapped_sector}, recommendations[:3]))
                    else: st.info("No stocks in this sector met the filter criteria.")
