import streamlit as st
import google.generativeai as genai
from tavily import TavilyClient
import yfinance as yf
import pandas as pd
import time

# --- PAGE CONFIG ---
st.set_page_config(page_title="AI Equity Researcher", page_icon="📈", layout="wide")
st.title("📈 Agentic Equity Research Assistant")

# --- 1. AUTHENTICATION ---
def load_api_keys():
    try:
        g_key = st.secrets["GOOGLE_API_KEY"]
        t_key = st.secrets["TAVILY_API_KEY"]
        return g_key, t_key, "✅ Authenticated via Secrets"
    except: pass
    
    with st.sidebar:
        st.header("🔐 Authentication")
        g_input = st.text_input("Gemini API Key", type="password")
        t_input = st.text_input("Tavily API Key", type="password")
        if not g_input or not t_input: return None, None, "⚠️ Waiting for Keys..."
        return g_input, t_input, "✅ Authenticated via Sidebar"

GOOGLE_API_KEY, TAVILY_API_KEY, status_msg = load_api_keys()

if "✅" in status_msg:
    st.success(status_msg)
else:
    st.warning(status_msg)
    st.stop()

genai.configure(api_key=GOOGLE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# --- 2. STRICT MODEL SELECTOR ---
@st.cache_resource
def get_high_quota_model():
    """
    Finds a model with HIGH limits (1.5 Flash).
    BANS 'gemini-2.5' or experimental models that cause 429 errors.
    """
    try:
        models = list(genai.list_models())
        
        # 1. Look specifically for the workhorse model (1500 req/day)
        for m in models:
            if 'gemini-1.5-flash' in m.name and '2.5' not in m.name:
                return m.name
        
        # 2. Fallback to Pro
        for m in models:
            if 'gemini-1.5-pro' in m.name:
                return m.name
                
        # 3. Last Resort (Standard Pro)
        for m in models:
            if 'gemini-pro' in m.name:
                return m.name
                
        return None
    except: return None

# --- 3. CACHED DATA ENGINES ---
@st.cache_data(ttl=3600)
def get_financials(ticker):
    try:
        t = ticker.upper().strip().replace(" ", "")
        if not t.endswith(".NS"): t += ".NS"
        stock = yf.Ticker(t)
        fin = stock.financials
        bs = stock.balance_sheet
        if fin.empty: return None, "No Data"
        
        years = fin.columns[:3]
        data = {}
        for date in years:
            yr = date.strftime('%Y')
            try:
                rev = fin.loc['Total Revenue', date] / 1e7
                pat = fin.loc['Net Income', date] / 1e7
                equity = bs.loc['Stockholders Equity', date] if 'Stockholders Equity' in bs.index else 1
                data[yr] = {"Rev(Cr)": round(rev,0), "PAT(Cr)": round(pat,0), "ROE%": round((pat*1e7/equity)*100, 1)}
            except: continue
        return pd.DataFrame(data).to_markdown(), None
    except Exception as e: return None, str(e)

@st.cache_data(ttl=3600)
def get_news(ticker):
    try:
        results = tavily.search(query=f"{ticker} share news india analysis", max_results=3)
        return "\n".join([f"- {r['title']}: {r['content'][:250]}..." for r in results['results']])
    except: return "News unavailable."

# --- 4. EXECUTION ---
ticker_list = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ITC", "SBIN", "TATAMOTORS", "ZOMATO"]
selected_ticker = st.selectbox("Select Company:", sorted(ticker_list))
generate_btn = st.button("🚀 Run Research")

if generate_btn:
    # Get the STRICT model
    model_name = get_high_quota_model()
    
    if not model_name:
        st.error("❌ Critical: No stable Gemini models found for this key.")
    else:
        st.toast(f"Using High-Quota Model: {model_name}") # Show user which model we picked
        
        with st.spinner(f"📊 Analyzing {selected_ticker}..."):
            fin_data, err = get_financials(selected_ticker)
            news_data = get_news(selected_ticker)
            
            if err:
                st.error(f"Data Error: {err}")
            else:
                prompt = f"""
                Analyst Report for **{selected_ticker}**.
                Data: {fin_data}
                News: {news_data}
                
                Write a 4-section investment report (Summary, Financials, Risks, Verdict).
                """
                
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt)
                    st.markdown("---")
                    st.subheader(f"📝 Report: {selected_ticker}")
                    st.markdown(response.text)
                except Exception as e:
                    if "429" in str(e):
                        st.error(f"❌ Your API Key is currently locked by Google. Please wait 5 minutes or use a new key.")
                    else:
                        st.error(f"AI Error: {e}")
