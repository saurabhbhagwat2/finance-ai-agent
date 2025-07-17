# app.py - FINAL, RESTRUCTURED VERSION

import streamlit as st
import pandas as pd
from textblob import TextBlob
import yfinance as yf
import requests
import logging
from io import StringIO
import time

# --- CONFIGURATION & CONSTANTS ---
try:
    TELEGRAM_TOKEN = st.secrets["telegram"]["token"]
    TELEGRAM_CHAT_ID = st.secrets["telegram"]["chat_id"]
except (KeyError, FileNotFoundError):
    st.info("Telegram credentials not found. Alerts will be disabled.")
    TELEGRAM_TOKEN = None
    TELEGRAM_CHAT_ID = None

NEWS_RSS_URL = "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"
STOCK_LIST_CSV = "nifty500_stocks_cleaned.csv"

SECTOR_KEYWORDS = {
    'AUTOMOBILE & AUTO COMPONENTS': ['auto', 'maruti', 'mahindra', 'tata motors', 'hero', 'bajaj', 'ev', 'automotive'],
    'PHARMA & HEALTHCARE': ['pharma', 'health', 'cipla', 'sun pharma', 'lupin', 'dr reddy', 'healthcare', 'vaccine'],
    'IT - SOFTWARE': ['it', 'tech', 'tcs', 'infosys', 'wipro', 'hcl', 'software', 'fintech'],
    'FINANCIAL SERVICES': ['bank', 'hdfc', 'icici', 'sbi', 'axis', 'finance', 'rbi', 'nbfc', 'insurance'],
    'OIL GAS & FUELS': ['oil', 'gas', 'ongc', 'reliance', 'bpcl', 'crude', 'energy', 'fuel'],
    'METALS & MINING': ['metal', 'steel', 'tata steel', 'jsw', 'hindalco', 'coal', 'mining'],
}
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ========= 📰 STEP 1: DATA INGESTION =========

@st.cache_data(ttl=1800)
def fetch_news_from_rss(url):
    """Fetches news headlines from the Google News RSS feed."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        df = pd.read_xml(StringIO(response.text))
        if 'title' in df.columns and 'link' in df.columns:
            st.success("✅ Successfully fetched latest news.")
            return df[['title', 'link']].head(20)
    except Exception as e:
        st.error(f"Failed to fetch news: {e}")
    return pd.DataFrame()

@st.cache_data
def load_nse_stocks():
    """Loads the master list of NIFTY 500 stocks and their industries from a CSV file."""
    try:
        df = pd.read_csv(STOCK_LIST_CSV)
        stock_column, industry_column = 'Symbol', 'Industry'
        if stock_column not in df.columns or industry_column not in df.columns:
            st.error(f"CRITICAL ERROR: CSV is missing '{stock_column}' or '{industry_column}'.")
            st.code(f"Columns found: {list(df.columns)}")
            return {}
        df[industry_column] = df[industry_column].str.upper().str.strip()
        st.success("✅ Successfully loaded the NIFTY 500 stock list.")
        return df.groupby(industry_column)[stock_column].apply(list).to_dict()
    except FileNotFoundError:
        st.error(f"CRITICAL ERROR: `{STOCK_LIST_CSV}` not found. Please upload it to GitHub.")
        return {}

# ========= 🧠 STEP 2: PROCESSING & ENRICHMENT =========

def analyze_sentiment(text):
    """Analyzes a headline, returning a sentiment label (POSITIVE/NEGATIVE) and a score."""
    text_cleaned = text.rsplit(' - ', 1)[0]
    analysis = TextBlob(text_cleaned)
    score = analysis.sentiment.polarity
    label = 'POSITIVE' if score > 0.1 else 'NEGATIVE' if score < -0.1 else 'NEUTRAL'
    return label, score

def map_headline_to_sector(headline):
    """Matches a headline to a predefined sector using keywords."""
    headline_lower = headline.lower()
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(keyword in headline_lower for keyword in keywords):
            return sector.upper()
    return None

# ========= 🔍 STEP 3: STOCK FILTERING & ANALYSIS =========

@st.cache_data(ttl=86400)
def analyze_stock_performance(symbol):
    """Analyzes a single stock's historical performance (average daily return)."""
    try:
        stock_data = yf.download(f"{symbol}.NS", period="6mo", progress=False)
        if stock_data.empty: return None
        return {'symbol': symbol, 'avg_return': stock_data['Close'].pct_change().mean()}
    except Exception:
        return None

# ========= ⚖️ STEP 4: DECISION ENGINE =========

def generate_recommendations(sentiment, stocks_to_analyze):
    """
    Applies the core BUY/AVOID logic based on sentiment and stock performance.
    This is the heart of the "AI" agent.
    """
    with st.spinner(f"Analyzing {len(stocks_to_analyze)} stocks..."):
        valid_stocks = [s for s in [analyze_stock_performance(s) for s in stocks_to_analyze] if s is not None]

    if sentiment == 'POSITIVE':
        # Rule: Keep stocks with positive historical performance trend.
        recommendations = [s for s in valid_stocks if s['avg_return'] > 0.001]
        # Sort by best performance first.
        return sorted(recommendations, key=lambda x: x['avg_return'], reverse=True)
    elif sentiment == 'NEGATIVE':
        # Rule: Keep stocks with negative historical performance trend.
        recommendations = [s for s in valid_stocks if s['avg_return'] < -0.001]
        # Sort by worst performance first.
        return sorted(recommendations, key=lambda x: x['avg_return'])
    return []

# ========= 📤 STEP 5: ALERTING & OUTPUT =========

def format_telegram_message(headline_info, recommendations):
    """Formats the final recommendation into a human-readable string for Telegram."""
    headline, sentiment, score, sector = headline_info.values()
    message = f"🚨 *AI Market Advisor Alert*\n\n📰 *Headline:* {headline}\n📊 *Sentiment:* {sentiment} (Score: {score:.2f})\n🏭 *Affected Sector:* {sector}\n\n"
    message += "📈 *Top BUY Recommendations:*\n" if sentiment == 'POSITIVE' else "📉 *Top AVOID Recommendations:*\n"
    if not recommendations:
        message += "_No stocks met the filter criteria._"
    else:
        for stock in recommendations:
            message += f"  - *{stock['symbol']}* (Avg Daily Return: {stock['avg_return'] * 100:.3f}%)\n"
    return message

def send_telegram_message(message):
    """Sends the formatted message to the configured Telegram chat."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        st.warning("Telegram is not configured.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    requests.post(url, json=payload)
    st.toast("✅ Alert sent to Telegram!")

# ========= MAIN ORCHESTRATOR & UI =========

@st.cache_data
def run_full_analysis(news_df, sector_stocks_map):
    """
    The main controller that runs the entire analysis pipeline (Steps 2-4)
    for all news headlines and returns a list of structured results.
    """
    results = []
    for _, row in news_df.iterrows():
        headline = row['title']
        sentiment, score = analyze_sentiment(headline)
        
        if sentiment != 'NEUTRAL':
            mapped_sector = map_headline_to_sector(headline)
            if mapped_sector:
                stocks_in_sector = sector_stocks_map.get(mapped_sector, [])
                if stocks_in_sector:
                    recommendations = generate_recommendations(sentiment, stocks_in_sector)
                    results.append({
                        'headline': headline.rsplit(' - ', 1)[0],
                        'sentiment': sentiment,
                        'score': score,
                        'sector': mapped_sector,
                        'recommendations': recommendations
                    })
    return results


st.set_page_config(page_title="AI Market Advisor", layout="wide")
st.title("📈 AI Market Advisor – News & Stock Picks")

# --- Sidebar for Controls and Status ---
with st.sidebar:
    st.header("Controls")
    if st.button("🔄 Clear Cache and Rerun"):
        st.cache_data.clear()
        st.rerun()
    st.header("Data Status")
    
    # --- Execute Step 1: Data Ingestion ---
    sector_stocks_map = load_nse_stocks()
    news_df = fetch_news_from_rss(NEWS_RSS_URL)
    
    st.warning("**Disclaimer:** This is for educational purposes. Not financial advice.")


# --- Main Page Layout ---
st.header("📰 Latest Business Headlines")
if news_df.empty:
    st.warning("Could not display news. Check status messages.")
else:
    st.dataframe(news_df, use_container_width=True, hide_index=True)

st.header("💬 Sentiment Analysis & Stock Suggestions")
if news_df.empty or not sector_stocks_map:
    st.warning("Analysis cannot run until all data is loaded successfully.")
else:
    # --- Run the full analysis pipeline ---
    analysis_results = run_full_analysis(news_df, sector_stocks_map)
    
    if not analysis_results:
        st.info("No news headlines matched the criteria for generating suggestions.")
    else:
        # --- Display the results ---
        for i, result in enumerate(analysis_results):
            emoji = "🟢" if result['sentiment'] == "POSITIVE" else "🔴"
            with st.expander(f"{emoji} [{result['sentiment']}] {result['headline']}"):
                st.markdown(f"**Sector:** `{result['sector']}` | **Sentiment Score:** `{result['score']:.2f}`")
                
                if not result['recommendations']:
                    st.info("No stocks in this sector met the strict filter criteria.")
                else:
                    st.write("**Top Recommendations:**")
                    rec_df = pd.DataFrame(result['recommendations'][:3])
                    rec_df['avg_return'] = rec_df['avg_return'].map('{:.3%}'.format)
                    st.dataframe(rec_df, use_container_width=True, hide_index=True)
                    
                    if st.button("Send Alert", key=f"send_{i}"):
                        message = format_telegram_message(result, result['recommendations'][:3])
                        send_telegram_message(message)
