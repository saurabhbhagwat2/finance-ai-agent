import streamlit as st
import requests
import pandas as pd
import yfinance as yf
from transformers import pipeline
from datetime import datetime, timedelta

st.set_page_config(layout="wide")
st.title("AI Market Advisor – NSE Stocks (Free Version)")

# 1. Fetch latest finance news headlines (via free RSS)
@st.cache_data()
def get_news():
    feed = requests.get("https://api.allorigins.win/raw?url=https://www.moneycontrol.com/rss/market-news/").text
    df = pd.read_xml(feed, xpath="//item/title")
    return df[0].tolist()

news = get_news()
st.subheader("Latest Headlines")
for idx, h in enumerate(news[:5]):
    st.write(f"**{idx+1}.** {h}")

# 2. Sentiment analysis
sentiment = pipeline("sentiment-analysis")
results = sentiment(news[:10])

sent_df = pd.DataFrame(results)
sent_df["headline"] = news[:10]
st.subheader("Sentiment Analysis (First 10)")
st.dataframe(sent_df)

# 3. Map keywords to sectors (basic logic)
sector_map = {
    "oil": "Energy",
    "bank": "Banking",
    "auto": "Auto",
    "steel": "Metal",
    "tech": "Technology",
    "pharma": "Pharma"
}
sent_df["sector"] = sent_df["headline"].str.lower().apply(lambda x: next((sector_map[k] for k in sector_map if k in x), "General"))

# 4. Load NSE 500 list (CSV)
@st.cache_data
def load_nse500():
    url = "https://raw.githubusercontent.com/zeetill/nse500/master/500.csv"
    df = pd.read_csv(url)
    return df

symbols = load_nse500()["SYMBOL"].unique().tolist()
st.markdown(f"Loaded {len(symbols)} NSE symbols")

# 5. Backtest function – calculate +1 day return avg/std
@st.cache_data(suppress_st_warning=True)
def backtest_symbol(sym):
    try:
        df = yf.download(sym + ".NS", period="6mo", progress=False)
        if df.empty:
            return None
        df["ret1"] = df["Adj Close"].pct_change().shift(-1)
        return df["ret1"].mean(), df["ret1"].std()
    except:
        return None

# 6. For each positive/negative sector, find top 3 stocks
st.subheader("Buy / Avoid Suggestions")
buy, avoid = [], []
for _, row in sent_df.iterrows():
    if row["label"] == "POSITIVE":
        for sym in symbols[:100]:  # limit to reduce load
            stats = backtest_symbol(sym)
            if stats and stats[0] > 0.001:
                buy.append((sym, stats))
    elif row["label"] == "NEGATIVE":
        for sym in symbols[:100]:
            stats = backtest_symbol(sym)
            if stats and stats[0] < -0.001:
                avoid.append((sym, stats))

st.markdown("**✅ Buy Candidates**")
st.write(buy[:5])

st.markdown("**❌ Avoid Candidates**")
st.write(avoid[:5])
