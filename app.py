import streamlit as st
import requests
import pandas as pd
import yfinance as yf
from transformers import pipeline
import io

st.set_page_config(layout="wide")
st.title("📈 AI Market Advisor – NSE Stocks (Live Version)")

# 1. Fetch NSE stock symbols (fixed version)
@st.cache_data(ttl=86400)
def get_all_nse_stocks():
    url = "https://www1.nseindia.com/content/equities/EQUITY_L.csv"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        df = pd.read_csv(io.StringIO(response.text), on_bad_lines='skip')  # ✅ skip malformed rows
        symbols = df["SYMBOL"].dropna().unique().tolist()
        return [s + ".NS" for s in symbols]
    except Exception as e:
        st.error(f"❌ Could not fetch NSE stock list: {e}")
        return []

# 2. Fetch latest finance news headlines from alternate RSS
@st.cache_data(ttl=3600)
def get_news():
    try:
        rss_url = "https://zeenews.india.com/rss/business.xml"
        response = requests.get(rss_url, timeout=10)
        df = pd.read_xml(response.content, xpath="//item")
        return df["title"].dropna().tolist()
    except Exception as e:
        st.error(f"❌ Failed to fetch or parse news: {e}")
        return []

# 3. Backtest logic
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

# Load data
symbols = get_all_nse_stocks()
news = get_news()
st.subheader("📰 Latest Headlines")

# Display news
if news:
    for i, headline in enumerate(news[:5]):
        st.write(f"**{i+1}.** {headline}")
else:
    st.warning("No news available right now.")

# Sentiment analysis
st.subheader("💬 Sentiment Analysis (Top 10 Headlines)")
if news:
    sentiment = pipeline("sentiment-analysis")
    results = sentiment(news[:10])
    sent_df = pd.DataFrame(results)
    sent_df["headline"] = news[:10]
else:
    sent_df = pd.DataFrame(columns=["label", "score", "headline"])

st.dataframe(sent_df)

# Map sectors
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

# Buy / Avoid logic
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
