import streamlit as st
import google.generativeai as genai
from tavily import TavilyClient
import yfinance as yf
import pandas as pd

# --- PAGE CONFIG ---
st.set_page_config(page_title="AI Equity Researcher", page_icon="📈", layout="wide")
st.title("📈 Agentic Equity Research Assistant")

# --- STEP 1: SMART KEY LOADER ---
# This function checks Secrets FIRST. If found, it ignores the sidebar.
def load_api_keys():
    # 1. Try to load from Streamlit Cloud Secrets
    try:
        g_key = st.secrets["GOOGLE_API_KEY"]
        t_key = st.secrets["TAVILY_API_KEY"]
        return g_key, t_key, "✅ Authenticated via Secrets"
    except (FileNotFoundError, KeyError):
        pass

    # 2. If no secrets, show Sidebar Inputs
    with st.sidebar:
        st.header("🔐 Authentication")
        g_input = st.text_input("Gemini API Key", type="password")
        t_input = st.text_input("Tavily API Key", type="password")
        
        if not g_input or not t_input:
            return None, None, "⚠️ Waiting for Keys..."
        return g_input, t_input, "✅ Authenticated via Sidebar"

# Load the keys immediately
GOOGLE_API_KEY, TAVILY_API_KEY, status_msg = load_api_keys()

# Show Status at the top
if "✅" in status_msg:
    st.success(status_msg)
else:
    st.warning(status_msg)
    st.stop()  # Stop the app here if no keys are found

# --- CONFIGURATION ---
genai.configure(api_key=GOOGLE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# --- STEP 2: ROBUST MODEL SELECTOR ---
def get_working_model():
    try:
        # Ask Google what models are available for this key
        models = list(genai.list_models())
        valid_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
        
        if not valid_models:
            return None
            
        # Preference List
        preferences = ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-pro']
        for p in preferences:
            if p in valid_models: return p
        return valid_models[0] # Fallback
    except:
        return None

# --- STEP 3: DATA ENGINES ---
def get_financials(ticker):
    try:
        t = ticker.replace(" ", "").upper() + ".NS"
        stock = yf.Ticker(t)
        fin = stock.financials
        bs = stock.balance_sheet
        if fin.empty: return None
        
        years = fin.columns[:3]
        data = {}
        for date in years:
            yr = date.strftime('%Y')
            try:
                rev = fin.loc['Total Revenue', date] / 1e7
                pat = fin.loc['Net Income', date] / 1e7
                equity = bs.loc['Stockholders Equity', date]
                data[yr] = {"Revenue(Cr)": round(rev,0), "PAT(Cr)": round(pat,0), "ROE%": round((pat*1e7/equity)*100, 1)}
            except: pass
        return pd.DataFrame(data).to_markdown()
    except: return None

def get_news(ticker):
    try:
        results = tavily.search(query=f"{ticker} share price news india frauds analysis", max_results=3)
        return "\n".join([f"- {r['title']}: {r['content'][:200]}..." for r in results['results']])
    except: return "News unavailable."

# --- STEP 4: MAIN UI ---
ticker = st.text_input("Enter Ticker (e.g. TCS, ZOMATO):").upper()
if st.button("🚀 Generate Report"):
    if not ticker:
        st.error("Please enter a ticker.")
    else:
        with st.spinner("🔍 Checking AI Connection..."):
            model_name = get_working_model()
            if not model_name:
                st.error("❌ API Key Error: Google Cloud blocked this key or no models found.")
            else:
                with st.spinner("📊 Gathering Financials & News..."):
                    fin_data = get_financials(ticker)
                    news_data = get_news(ticker)
                    
                    if not fin_data:
                        st.error("❌ Could not fetch financial data. Check Ticker.")
                    else:
                        with st.spinner("✍️ Writing Report..."):
                            prompt = f"""
                            You are a Senior Analyst. Write a research report for {ticker}.
                            
                            [FINANCIALS]
                            {fin_data}
                            
                            [NEWS]
                            {news_data}
                            
                            Output:
                            1. Executive Summary
                            2. Financial Health (Analyze Revenue/ROE trends)
                            3. Risk Analysis (Based on news)
                            4. Verdict (Buy/Sell/Hold)
                            """
                            model = genai.GenerativeModel(model_name)
                            response = model.generate_content(prompt)
                            st.markdown("---")
                            st.markdown(response.text)
