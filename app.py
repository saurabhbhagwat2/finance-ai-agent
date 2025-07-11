# app.py

import streamlit as st
import pandas as pd
from textblob import TextBlob
import yfinance as yf
import requests
import logging
from io import StringIO # Needed for the news fix

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

# --- Keywords mapping. Make sure sector names match the 'Industry' column in the CSV ---
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

# --- FIX #2: More robust news fetching ---
@st.cache_data(ttl=3600) # Cache for 1 hour
def fetch_news_from_rss(url):
    """Fetches news headlines from an RSS feed robustly and caches the result."""
    try:
        logging.info("Fetching fresh news from RSS feed.")
        # Use requests to act like a browser, which is more reliable
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # This will raise an error for bad responses (like 404, 503)

        # Use StringIO to read the text content as if it were a file
        xml_content = StringIO(response.text)
        df = pd.read_xml(xml_content)
        
        if 'title' in df.columns and 'link' in df.columns:
            return df[['title', 'link']].head(15)
        else:
            st.error("RSS feed is valid but is missing 'title' or 'link' columns.")
            return pd.DataFrame()
            
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to fetch news (network error): {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Failed to parse the news feed. The format might have changed. Error: {e}")
        return pd.DataFrame()

# --- FIX #1: More robust stock list loading ---
@st.cache_data
def load_nse_stocks():
    """Loads NSE stock list from CSV and handles potential column name errors."""
    try:
        df = pd.read_csv(STOCK_LIST_CSV)
        
        # Define expected column names (NSE often uses 'Symbol' with a capital S)
        stock_column = 'Symbol' 
        industry_column = 'Industry'

        # Check if the columns exist before using them
        if stock_column not in df.columns:
            st.error(f"Could not find the stock ticker column '{stock_column}' in your CSV.")
            st.info(f"👉 **FIX:** Open your CSV file and find the correct column name for stock tickers. The available columns are: {list(df.columns)}")
            return {}
        
        if industry_column not in df.columns:
            st.error(f"Could not find the industry column '{industry_column}' in your CSV.")
            st.info(f"👉 **FIX:** Open your CSV file and find the correct column name for industries. The available columns are: {list(df.columns)}")
            return {}

        df[industry_column] = df[industry_column].str.upper().str.strip()
        sector_stocks = df.groupby(industry_column)[stock_column].apply(list).to_dict()
        return sector_stocks
        
    except FileNotFoundError:
        st.error(f"Stock list file `{STOCK_LIST_CSV}` not found. Please make sure it's uploaded to your GitHub repository.")
        return {}
    except Exception as e:
        st.error(f"An unexpected error occurred while loading the stock CSV: {e}")
        return {}


# ========= ANALYSIS & HELPER FUNCTIONS (No changes needed here) =========

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
    message = f"🚨 *AI Market Advisor Alert*\n\n"
    message += f"📰 *Headline:* {headline}\n"
    message += f"📊 *Sentiment:* {sentiment} (Score: {score:.2f})\n"
    message += f"🏭 *Affected Sector:* {sector}\n\n"
    
    if sentiment == 'POSITIVE':
        message += "📈 *Top BUY Recommendations:*\n"
    else:
        message += "📉 *Top AVOID Recommendations:*\n"
    
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
        if response.status_code == 200:
            st.toast("✅ Alert sent to Telegram!")
        else:
            st.error(f"Failed to send Telegram message: {response.text}")
    except Exception as e:
        st.error(f"Exception while sending Telegram message: {e}")

# ========= STREAMLIT UI (Slightly reorganized for better flow) =========

st.set_page_config(page_title="AI Market Advisor", layout="wide")
st.title("📈 AI Market Advisor – NSE Stocks (Live Version)")

st.sidebar.header("Controls")
if st.sidebar.button("🔄 Clear Cache and Rerun"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.warning(
    "**Disclaimer:** This is an AI-generated analysis for educational purposes. Not financial advice."
)

# --- Main App Logic ---
sector_stocks_map = load_nse_stocks()
news_df = fetch_news_from_rss(NEWS_RSS_URL)

st.header("📰 Latest Headlines")
if news_df.empty:
    st.warning("Could not display news. Please check the error messages above.")
else:
    st.dataframe(news_df, use_container_width=True, hide_index=True)

st.header("💬 Sentiment Analysis & Stock Suggestions")
if news_df.empty or not sector_stocks_map:
    st.warning("Analysis cannot run until the data loading issues above are resolved.")
else:
    found_suggestions = False
    for index, row in news_df.iterrows():
        headline = row['title']
        sentiment, score = analyze_sentiment(headline)
        
        if sentiment != 'NEUTRAL':
            mapped_sector = map_headline_to_sector(headline)
            
            if mapped_sector:
                found_suggestions = True
                sentiment_emoji = "🟢" if sentiment == "POSITIVE" else "🔴"
                expander_title = f"{sentiment_emoji} [{sentiment}] {headline}"

                with st.expander(expander_title):
                    st.markdown(f"**Sector:** `{mapped_sector}` | **Sentiment Score:** `{score:.2f}`")
                    
                    stocks_in_sector = sector_stocks_map.get(mapped_sector, [])
                    if not stocks_in_sector:
                        st.warning("No stocks found for this sector. The industry name might be different in your CSV file.")
                        continue
                    
                    with st.spinner(f"Analyzing {len(stocks_in_sector)} stocks in {mapped_sector}..."):
                        all_stock_analysis = [analyze_stock_performance(s) for s in stocks_in_sector]
                        valid_stocks = [s for s in all_stock_analysis if s is not None]

                    recommendations = []
                    if sentiment == 'POSITIVE':
                        recommendations = [s for s in valid_stocks if s['avg_return'] > 0.001]
                        recommendations.sort(key=lambda x: x['avg_return'], reverse=True)
                    else:
                        recommendations = [s for s in valid_stocks if s['avg_return'] < -0.001]
                        recommendations.sort(key=lambda x: x['avg_return'])
                    
                    if recommendations:
                        rec_df = pd.DataFrame(recommendations[:3])
                        rec_df['avg_return'] = rec_df['avg_return'].map('{:.3%}'.format)
                        st.dataframe(rec_df, use_container_width=True, hide_index=True)
                        
                        alert_key = f"send_{index}"
                        if st.button("Send This Alert to Telegram", key=alert_key):
                            headline_info = {'title': headline, 'sentiment': sentiment, 'score': score, 'sector': mapped_sector}
                            message = format_telegram_message(headline_info, recommendations[:3])
                            send_telegram_message(message)
                    else:
                        st.info("No stocks in this sector met the filter criteria.")
    if not found_suggestions:
        st.info("No headlines matched the keyword filters for sector analysis.")
