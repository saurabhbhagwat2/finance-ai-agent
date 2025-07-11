import streamlit as st
import requests
import pandas as pd
import yfinance as yf
from transformers import pipeline

st.set_page_config(layout="wide")
st.title("📈 AI Market Advisor – NSE Stocks (Live Version)")

# 1. Fetch NSE stock symbols daily
@st.cache_data(ttl=86400)
def get_all_nse_stocks():
    url = "https://www1.nseindia.com/content/equities/EQUITY_L.csv"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    try:
        df = pd.read_csv(url, usecols=["SYMBOL"], storage_options={"headers": headers})
        symbols = df["SYMBOL"].dropna().unique().tolist()
        return [s + ".NS" for s in symbols]
    except Exception as e:
        st.error(f"❌ Could not fetch NSE stock list: {e}")
        return []

# 2. Fetch latest headlines from Moneycontrol RSS
@st.cache_data(ttl=3600)
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

# 3. Perform backtest
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

# 📥 Load everything
symbols = get_all_nse_stocks()
news = get_news()
st.subheader("📰 Latest Headlines")

# 📰 Show top 5 news
if news:
    for i, headline in enumerate(news[:5]):
        st.write(f"**{i+1}.** {headline}")
else:
    st.warning("No news available right now.")

# 🔍 Sentiment analysis
st.subheader("💬 Sentiment Analysis (Top 10 Headlines)")
if news:
    sentiment = pipeline("sentiment-analysis")
    results = sentiment(news[:10])
    sent_df = pd.DataFrame(results)
    sent_df["headline"] = news[:10]
else:
    sent_df = pd.DataFrame(columns=["label", "score", "headline"])

st.dataframe(sent_df)

# 🔗 Sector map
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

# 📊 Buy / Avoid Suggestions
st.subheader("📌 Buy / Avoid Suggestions")
buy, avoid = [], []

if not sent_df.empty:
    for _, row in sent_df.iterrows():
        label = row["label"]
        if label not in ["POSITIVE", "NEGATIVE"]:
            continue
        for sym in symbols[:100]:  # limit to 100 for speed
            stats = backtest_symbol(sym)
            if not stats:
                continue
            avg_ret, std_dev = stats
            if label == "POSITIVE" and avg_ret > 0.001:
                buy.append((sym, avg_ret, std_dev))
            elif label == "NEGATIVE" and avg_ret < -0.001:
                avoid.append((sym, avg_ret, std_dev))

    # Display tables
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
