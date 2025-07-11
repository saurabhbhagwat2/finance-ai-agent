# app.py

import streamlit as st
import pandas as pd
from textblob import TextBlob
import yfinance as yf
import requests
import logging
from io import StringIO

# --- CONFIGURATION (using Streamlit Secrets) ---
try:
    TELEGRAM_TOKEN = st.secrets["telegram"]["token"]
    TELEGRAM_CHAT_ID = st.secrets["telegram"]["chat_id"]
except (KeyError, FileNotFoundError):
    st.info("Telegram credentials not found. Alerts will be disabled.")
    TELEGRAM_TOKEN = None
    TELEGRAM_CHAT_ID = None

# --- CONSTANTS ---
NEWS_RSS_URL = "https://www.moneycontrol.com/rss/business.xml"
STOCK_LIST_CSV = "nifty500_stocks.csv"

# --- Keywords mapping. Sector names here MUST MATCH the names in your CSV's 'Industry' column ---
# I have made them uppercase to match the code's logic.
SECTOR_KEYWORDS = {
    'AUTOMOBILE & AUTO COMPONENTS': ['auto', 'maruti', 'mahindra', 'tata motors', 'hero', 'bajaj', 'ev'],
    'PHARMA & HEALTHCARE': ['pharma', 'health', 'cipla', 'sun pharma', 'lupin', 'dr reddy', 'healthcare'],
    'IT - SOFTWARE': ['it', 'tech', 'tcs', 'infosys', 'wipro', 'hcl', 'software'],
    'FINANCIAL SERVICES': ['bank', 'hdfc', 'icici', 'sbi', 'axis', 'finance', 'rbi', 'nbfc'],
    'OIL GAS & FUELS': ['oil', 'gas', 'ongc', 'reliance', 'bpcl', 'crude', 'energy'],
    'METALS & MINING': ['metal', 'steel', 'tata steel', 'jsw', 'hindalco', 'coal', 'mining'],
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ========= CACHED DATA LOADING FUNCTIONS (WITH FIXES) =========

@st.cache_data(ttl=3600)
def fetch_news_from_rss(url):
    """Fetches news headlines from an RSS feed robustly."""
    try:
        logging.info("Fetching fresh news from RSS feed.")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
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

@st.cache_data
def load_nse_stocks():
    """Loads NSE stock list from CSV and handles column name errors."""
    try:
        df = pd.read_csv(STOCK_LIST_CSV)
        
        # <<< --- THIS IS THE MOST IMPORTANT PART TO FIX THE 'SYMBOL' ERROR --- >>>
        # The NSE CSV usually has 'Symbol' (capital S) and 'Industry'.
        stock_column = 'Symbol' 
        industry_column = 'Industry'

        if stock_column not in df.columns:
            st.error(f"CRITICAL ERROR: Could not find the stock ticker column named '{stock_column}' in your CSV file.")
            st.info(f"👉 **ACTION REQUIRED:** Open your `{STOCK_LIST_CSV}` file on GitHub. Find the correct column name for stock tickers and change the line `stock_column = '{stock_column}'` in the code to match it.")
            st.code(f"The columns I found are: {list(df.columns)}")
            return {}
        
        if industry_column not in df.columns:
            st.error(f"CRITICAL ERROR: Could not find the industry column named '{industry_column}' in your CSV file.")
            st.info(f"👉 **ACTION REQUIRED:** Find the correct column name for industries and change `industry_column = '{industry_column}'` in the code.")
            st.code(f"The columns I found are: {list(df.columns)}")
            return {}

        df[industry_column] = df[industry_column].str.upper().str.strip()
        sector_stocks = df.groupby(industry_column)[stock_column].apply(list).to_dict()
        return sector_stocks
        
    except FileNotFoundError:
        st.error(f"CRITICAL ERROR: Stock list file `{STOCK_LIST_CSV}` not found. Please make sure it's uploaded to your GitHub repository.")
        return {}
    except Exception as e:
        st.error(f"An unexpected error occurred while loading the stock CSV: {e}")
        return {}

# ========= ANALYSIS & HELPER FUNCTIONS (No changes needed) =========
# All functions below this line are correct.

def analyze_sentiment(text):
    analysis = TextBlob(text)
    polarity = analysis.sentiment.polarity
    label = 'POSITIVE' if polarity > 0.1 else 'NEGATIVE' if polarity < -0.1 else 'NEUTRAL'
    return label, polarity

def map_headline_to_sector(headline):
    headline_lower = headline.lower()
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(keyword in headline_lower for keyword in keywords):
            return sector
    return None

@st.cache_data(ttl=86400)
def analyze_stock_performance(symbol):
    try:
        stock_data = yf.download(f"{symbol}.NS", period="6mo", progress=False)
        if stock_data.empty: return None
        stock_data['daily_return'] = stock_data['Close'].pct_change()
        avg_return = stock_data['daily_return'].mean()
        return {'symbol': symbol, 'avg_return': avg_return}
    except Exception:
        return None

def format_telegram_message(headline_info, recommendations):
    headline, sentiment, score, sector = headline_info.values()
    message = f"🚨 *AI Market Advisor Alert*\n\n📰 *Headline:* {headline}\n📊 *Sentiment:* {sentiment} (Score: {score:.2f})\n🏭 *Affected Sector:* {sector}\n\n"
    message += "📈 *Top BUY Recommendations:*\n" if sentiment == 'POSITIVE' else "📉 *Top AVOID Recommendations:*\n"
    if not recommendations:
        message += "_No stocks met the filter criteria._"
    else:
        for stock in recommendations:
            avg_ret_pct = stock['avg_return'] * 100
            message += f"  - *{stock['symbol']}* (Avg Daily Return: {avg_ret_pct:.3f}%)\n"
    return message

def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        st.warning("Telegram is not configured. Message not sent.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200: st.toast("✅ Alert sent to Telegram!")
        else: st.error(f"Failed to send Telegram message: {response.text}")
    except Exception as e: st.error(f"Exception while sending Telegram message: {e}")

# ========= STREAMLIT UI =========

st.set_page_config(page_title="AI Market Advisor", layout="wide")
st.title("📈 AI Market Advisor – NSE Stocks (Live Version)")

st.sidebar.header("Controls")
if st.sidebar.button("🔄 Clear Cache and Rerun"):
    st.cache_data.clear()
    st.rerun()
st.sidebar.warning("**Disclaimer:** This is for educational purposes. Not financial advice.")

sector_stocks_map = load_nse_stocks()
news_df = fetch_news_from_rss(NEWS_RSS_URL)

st.header("📰 Latest Headlines")
if news_df.empty:
    st.warning("Could not display news. Please check error messages at the top of the page.")
else:
    st.dataframe(news_df, use_container_width=True, hide_index=True)

st.header("💬 Sentiment Analysis & Stock Suggestions")
if news_df.empty or not sector_stocks_map:
    st.warning("Analysis cannot run until the data loading issues are resolved.")
else:
    found_suggestions = False
    for index, row in news_df.iterrows():
        headline, sentiment, score = row['title'], *analyze_sentiment(row['title'])
        if sentiment != 'NEUTRAL':
            mapped_sector = map_headline_to_sector(headline)
            if mapped_sector:
                found_suggestions = True
                expander_title = f"{'🟢' if sentiment == 'POSITIVE' else '🔴'} [{sentiment}] {headline}"
                with st.expander(expander_title):
                    st.markdown(f"**Sector:** `{mapped_sector}` | **Sentiment Score:** `{score:.2f}`")
                    stocks_in_sector = sector_stocks_map.get(mapped_sector, [])
                    if not stocks_in_sector:
                        st.warning(f"No stocks found for '{mapped_sector}'. Check if this sector name exists in your CSV's 'Industry' column.")
                        continue
                    with st.spinner(f"Analyzing {len(stocks_in_sector)} stocks..."):
                        valid_stocks = [s for s in [analyze_stock_performance(s) for s in stocks_in_sector] if s is not None]
                    
                    if sentiment == 'POSITIVE': recommendations = sorted([s for s in valid_stocks if s['avg_return'] > 0.001], key=lambda x: x['avg_return'], reverse=True)
                    else: recommendations = sorted([s for s in valid_stocks if s['avg_return'] < -0.001], key=lambda x: x['avg_return'])
                    
                    if recommendations:
                        rec_df = pd.DataFrame(recommendations[:3])
                        rec_df['avg_return'] = rec_df['avg_return'].map('{:.3%}'.format)
                        st.dataframe(rec_df, use_container_width=True, hide_index=True)
                        if st.button("Send This Alert to Telegram", key=f"send_{index}"):
                            send_telegram_message(format_telegram_message({'title': headline, 'sentiment': sentiment, 'score': score, 'sector': mapped_sector}, recommendations[:3]))
                    else:
                        st.info("No stocks in this sector met the filter criteria.")
    if not found_suggestions:
        st.info("No headlines matched the keyword filters for sector analysis.")
