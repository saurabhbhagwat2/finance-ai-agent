import streamlit as st
import requests
import pandas as pd
import yfinance as yf
from textblob import TextBlob
import xml.etree.ElementTree as ET
import io

st.set_page_config(layout="wide")
st.title("📈 AI Market Advisor – NSE Stocks (Live Version)")

# 1. Get NIFTY 500 symbols
@st.cache_data(ttl=86400)
def get_nse_symbols():
    try:
        url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500"
        headers = {"User-Agent": "Mozilla/5.0"}
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers)
        res = session.get(url, headers=headers, timeout=10)
        data = res.json()
        return [item["symbol"] + ".NS" for item in data["data"]]
    except Exception as e:
        st.error(f"❌ Could not fetch NSE stock list: {e}")
        return []

# 2. Get news from RSS feed (clean XML)
@st.cache_data(ttl=3600)
def get_news():
    try:
        rss_url = "https://zeenews.india.com/rss/business.xml"
        response = requests.get(rss_url, timeout=10)
        raw = response.content.decode("utf-8").lstrip()  # strip whitespace
        xml_tree = ET.ElementTree(ET.fromstring(raw))
        items = xml_tree.findall(".//item/title")
        return [item.text for item in items if item is not None]
    except Exception as e:
        st.error(f"❌ Failed to fetch or parse news: {e}")
        return []

# 3. Backtest
@st.cache_data
def backtest_symbol(sym):
    try:
        df = yf.download(sym, period="6mo", progress=False)
        if df.empty:
            return None
        df["ret1"] = df["Adj Close"].pct_change().shift(-1)
        return df["ret1"].mean(), df["ret1"].std()
    except:
        return None

# 4. TextBlob sentiment
def analyze_sentiment(text):
    blob = TextBlob(text)
    return "POSITIVE" if blob.sentiment.polarity > 0 else "NEGATIVE"

# Load data
symbols = get_nse_symbols()
news = get_news()

st.subheader("📰 Latest Headlines")
if news:
    for i, headline in enumerate(news[:5]):
        st.write(f"**{i+1}.** {headline}")
else:
    st.warning("No news available right now.")

# Sentiment
st.subheader("💬 Sentiment Analysis (Top 10 Headlines)")
if news:
    sent_df = pd.DataFrame(news[:10], columns=["headline"])
    sent_df["label"] = sent_df["headline"].apply(analyze_sentiment)
    sent_df["score"] = sent_df["headline"].apply(lambda x: round(TextBlob(x).sentiment.polarity, 2))
else:
    sent_df = pd.DataFrame(columns=["headline", "label", "score"])

st.dataframe(sent_df)

# Sector Mapping
sector_map = {
    "oil": "Energy",
    "bank": "Banking",
    "auto": "Auto",
    "steel": "Metal",
    "tech": "Technology",
    "pharma": "Pharma"
}
sent_df["sector"] = sent_df["headline"].str.lower().apply(
    lambda x: next((sector_map[k] for k in sector_map if k in x), "General")
)

# Buy / Avoid Logic
st.subheader("📌 Buy / Avoid Suggestions")
buy, avoid = [], []

if not sent_df.empty:
    for _, row in sent_df.iterrows():
        label = row["label"]
        if label not in ["POSITIVE", "NEGATIVE"]:
            continue
        for sym in symbols[:100]:
            stats = backtest_symbol(sym)
            if not stats:
                continue
            avg_ret, std_dev = stats
            if label == "POSITIVE" and avg_ret > 0.001:
                buy.append((sym, avg_ret, std_dev))
            elif label == "NEGATIVE" and avg_ret < -0.001:
                avoid.append((sym, avg_ret, std_dev))

    st.markdown("### ✅ Buy Candidates")
    if buy:
        buy_df = pd.DataFrame(buy, columns=["Symbol", "Avg Return", "Std Dev"])
        st.dataframe(buy_df.sort_values("Avg Return", ascending=False).head(5))
    else:
        st.info("No buy suggestions found.")

    st.markdown("### ❌ Avoid Candidates")
    if avoid:
        avoid_df = pd.DataFrame(avoid, columns=["Symbol", "Avg Return", "Std Dev"])
        st.dataframe(avoid_df.sort_values("Avg Return").head(5))
    else:
        st.info("No avoid suggestions found.")
else:
    st.warning("Sentiment analysis could not run due to missing headlines.")
