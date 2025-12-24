import streamlit as st
import google.generativeai as genai
from tavily import TavilyClient
import yfinance as yf
import pandas as pd
import time
import random

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="AI Equity Researcher",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Agentic Equity Research Assistant")

# --- 1. AUTHENTICATION ---
def load_api_keys():
    try:
        g_key = st.secrets["GOOGLE_API_KEY"]
        t_key = st.secrets["TAVILY_API_KEY"]
        return g_key, t_key, "✅ Authenticated via Secrets"
    except (FileNotFoundError, KeyError):
        pass

    with st.sidebar:
        st.header("🔐 Authentication")
        g_input = st.text_input("Gemini API Key", type="password")
        t_input = st.text_input("Tavily API Key", type="password")
        if not g_input or not t_input:
            return None, None, "⚠️ Waiting for Keys..."
        return g_input, t_input, "✅ Authenticated via Sidebar"

GOOGLE_API_KEY, TAVILY_API_KEY, status_msg = load_api_keys()

if "✅" in status_msg:
    st.success(status_msg)
else:
    st.warning(status_msg)
    st.stop() 

genai.configure(api_key=GOOGLE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# --- 2. CACHED MODEL SELECTOR (Saves Quota) ---
@st.cache_resource
def get_working_model_cached():
    """
    Checks available models ONCE and remembers the result.
    This prevents hitting the API limit just to check model names.
    """
    try:
        models = list(genai.list_models())
        valid_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
        
        if not valid_models: return None
        
        # Priority: Flash (Fastest) -> Pro (Smarter)
        priority = ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-pro']
        for p in priority:
            if p in valid_models: return p
        return valid_models[0]
    except: return None

# --- 3. CACHED DATA ENGINES (Saves Time) ---
@st.cache_data(ttl=3600) # Remember data for 1 hour
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

# --- 4. SMART GENERATOR (With Fallback) ---
def generate_report(model_name, prompt):
    model = genai.GenerativeModel(model_name)
    try:
        return model.generate_content(prompt).text
    except Exception as e:
        if "429" in str(e) or "Quota" in str(e):
            # If Flash fails, try Pro as a backup (sometimes has different quota bucket)
            try:
                fallback_model = 'models/gemini-pro'
                st.warning(f"⚠️ Quota hit on {model_name}. Switching to {fallback_model}...")
                time.sleep(2)
                backup = genai.GenerativeModel(fallback_model)
                return backup.generate_content(prompt).text
            except:
                return "❌ DAILY QUOTA EXCEEDED. Please wait 2-3 minutes."
        return f"Error: {e}"

# --- 5. UI ---
ticker_list = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ITC", "SBIN", "TATAMOTORS", "ZOMATO"]
selected_ticker = st.selectbox("Select Company:", sorted(ticker_list))
generate_btn = st.button("🚀 Run Research")

if generate_btn:
    # Use cached model function
    model_name = get_working_model_cached()
    
    if not model_name:
        st.error("❌ API Error: No models found.")
    else:
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
                
                # Run Generation
                report = generate_report(model_name, prompt)
                
                if "❌" in report:
                    st.error(report)
                else:
                    st.markdown("---")
                    st.subheader(f"📝 Report: {selected_ticker}")
                    st.markdown(report)
