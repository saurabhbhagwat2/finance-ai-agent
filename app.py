import streamlit as st
import requests
import pandas as pd
import yfinance as yf
from transformers import pipeline
from datetime import datetime

# Page config
st.set_page_config(layout="wide")
st.title("📈 AI Market Advisor – NSE Stocks (Free Version)")

# 1. Fetch latest finance news headlines (via RSS)
@st.cache_data
def get_news():
    try:
        rss_url = "https://api.allorigins.win/raw?url=https://www.moneycontrol.com/rss/market-news/"
        response = requests.get(rss_url, timeout=10)
        if response.status_code != 200:
            return []

        df = pd.read_xml(response.content, xpath="//item")
        return df["title"].dropna().tolist()
    except Exception as e:
        st.error(f"❌ Failed to fetch or parse news: {e}")
        return []

news = get_news()

st.subheader("📰 Latest Headlines")
if news:
    for idx, h in enumerate(news[:5]):
        st.write(f"**{idx+1}.** {h}")
else:
    st.warning("No news available right now.")

# 2. Sentiment analysis on news headlines
st.subheader("💬 Sentiment Analysis (Top 10 Headlines)")
if news:
    sentiment = pipeline("sentiment-analysis")
    results = sentiment(news[:10])
    sent_df = pd.DataFrame(results)
    sent_df["headline"] = news[:10]
else:
    sent_df = pd.DataFrame(columns=["label", "score", "headline"])

st.dataframe(sent_df)

# 3. Map keywords to sectors
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

# 4. Load NSE 500 list
@st.cache_data
def load_nse500():
    url = "https://raw.githubusercontent.com/zeetill/nse500/master/500.csv"
    try:
        df = pd.read_csv(url)
        return df
    except Exception as e:
        st.error(f"Failed to load NSE 500 list: {e}")
        return pd.DataFrame()

nse_df = load_nse500()
symbols = nse_df["SYMBOL"].unique().tolist()
st.markdown(f"✅ Loaded `{len(symbols)}` NSE symbols")

# 5. Backtest stock returns (next-day return)
@st.cache_data
def backtest_symbol(sym):
    try:
        df = yf.download(sym + ".NS", period="6mo", progress=False)
        if df.empty:
            return None
        df["ret1"] = df["Adj Close"].pct_change().shift(-1)
        return df["ret1"].mean(), df["ret1"].std()
    except:
        return None

# 6. Based on sentiment, recommend buy/avoid
st.subheader("📌 Buy / Avoid Suggestions")

buy, avoid = [], []

if not sent_df.empty:
    for _, row in sent_df.iterrows():
        sentiment_label = row["label"]
        if sentiment_label not in ["POSITIVE", "NEGATIVE"]:
            continue

        for sym in symbols[:100]:  # Limit to 100 stocks to reduce API load
            stats = backtest_symbol(sym)
            if not stats:
                continue

            avg_return, std_dev = stats

            if sentiment_label == "POSITIVE" and avg_return > 0.001:
                buy.append((sym, avg_return, std_dev))
            elif sentiment_label == "NEGATIVE" and avg_return < -0.001:
                avoid.append((sym, avg_return, std_dev))

    # Display top 5 from each list
    st.markdown("### ✅ Suggested Buy Candidates")
    if buy:
        buy_df = pd.DataFrame(buy, columns=["Symbol", "Avg Return", "Std Dev"])
        st.dataframe(buy_df.sort_values("Avg Return", ascending=False).head(5))
    else:
        st.info("No buy suggestions based on current sentiment.")

    st.markdown("### ❌ Suggested Avoid Candidates")
    if avoid:
        avoid_df = pd.DataFrame(avoid, columns=["Symbol", "Avg Return", "Std Dev"])
        st.dataframe(avoid_df.sort_values("Avg Return").head(5))
    else:
        st.info("No avoid suggestions based on current sentiment.")
else:
    st.warning("❗ No headlines or sentiment to evaluate suggestions.")
