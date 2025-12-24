import streamlit as st
import google.generativeai as genai
from tavily import TavilyClient
import yfinance as yf
import pandas as pd
import time

# --- PAGE CONFIG ---
st.set_page_config(page_title="AI Equity Researcher", page_icon="📈", layout="wide")
st.title("📈 Agentic Equity Research Assistant")

# --- 1. AUTHENTICATION (With Verifier) ---
def get_keys():
    # 1. Try Secrets
    try:
        g_key = st.secrets["GOOGLE_API_KEY"]
        t_key = st.secrets["TAVILY_API_KEY"]
        return g_key, t_key, "✅ Secrets"
    except: pass
    
    # 2. Sidebar Input
    with st.sidebar:
        st.header("🔐 Authentication")
        g_input = st.text_input("Gemini API Key", type="password")
        t_input = st.text_input("Tavily API Key", type="password")
        if g_input and t_input:
            return g_input, t_input, "✅ Sidebar"
        return None, None, "Waiting"

GOOGLE_KEY, TAVILY_KEY, source = get_keys()

if not GOOGLE_KEY:
    st.warning("⚠️ Please enter API Keys to start.")
    st.stop()
else:
    # KEY VERIFIER: Show last 4 digits to prove it's the NEW key
    st.sidebar.success(f"{source} Loaded! (Ends in ...{GOOGLE_KEY[-4:]})")

# Configure Clients
genai.configure(api_key=GOOGLE_KEY)
tavily = TavilyClient(api_key=TAVILY_KEY)

# --- 2. DATA ENGINES ---
@st.cache_data(ttl=3600)
def get_financials(ticker):
    try:
        t = ticker.upper().strip().replace(" ", "")
        if not t.endswith(".NS"): t += ".NS"
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
                equity = bs.loc['Stockholders Equity', date] if 'Stockholders Equity' in bs.index else 1
                data[yr] = {"Rev(Cr)": round(rev,0), "PAT(Cr)": round(pat,0), "ROE%": round((pat*1e7/equity)*100, 1)}
            except: continue
        return pd.DataFrame(data).to_markdown()
    except: return None

@st.cache_data(ttl=3600)
def get_news(ticker):
    try:
        results = tavily.search(query=f"{ticker} share news india analysis", max_results=3)
        return "\n".join([f"- {r['title']}: {r['content'][:250]}..." for r in results['results']])
    except: return "News unavailable."

# --- 3. BLIND GENERATOR (No Model Listing) ---
def run_agent_blind(ticker):
    # HARDCODED: We skip the check and go straight to the standard model
    # This saves 1 API Call per run.
    model = genai.GenerativeModel('models/gemini-1.5-flash')
    
    fin_data = get_financials(ticker)
    if not fin_data: return "❌ Error: Could not fetch financial data."
    
    news_data = get_news(ticker)
    
    prompt = f"""
    You are a Senior Analyst. Write a short investment report for **{ticker}**.
    
    [FINANCIALS]
    {fin_data}
    
    [NEWS]
    {news_data}
    
    Output:
    1. Business Summary
    2. Financial Health (Revenue/ROE Trends)
    3. Risks
    4. Verdict (Buy/Sell/Hold)
    """
    
    try:
        # Retry Logic built-in
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        if "429" in str(e):
            st.warning("⏳ Limit Hit. Waiting 5 seconds and retrying...")
            time.sleep(5)
            try:
                return model.generate_content(prompt).text
            except:
                return "❌ DAILY LIMIT REACHED. Please change API Key."
        elif "404" in str(e):
            # Fallback for older keys
            try:
                backup = genai.GenerativeModel('models/gemini-pro')
                return backup.generate_content(prompt).text
            except:
                return "❌ Error: No models available for this key."
        return f"Error: {e}"

# --- 4. UI ---
ticker_list = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ITC", "SBIN", "ZOMATO"]
selected = st.selectbox("Select Company:", sorted(ticker_list))

if st.button("🚀 Run Research"):
    with st.spinner("Running..."):
        report = run_agent_blind(selected)
        if "❌" in report:
            st.error(report)
        else:
            st.markdown("---")
            st.subheader(f"📝 Report: {selected}")
            st.markdown(report)
