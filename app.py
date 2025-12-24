import streamlit as st
import google.generativeai as genai
from tavily import TavilyClient
import yfinance as yf
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="AI Equity Researcher",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Agentic Equity Research Assistant")
st.markdown("Generates a professional Investment Report using **Live Financials** (Yahoo Finance) + **Web Search** (Tavily).")

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

# --- 2. ROBUST MODEL SELECTOR (FIXED PRIORITY) ---
def get_working_model():
    try:
        models = list(genai.list_models())
        valid_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
        
        # PRIORITY FIX: Put the high-quota stable models FIRST
        # gemini-1.5-flash = 1,500 requests per day (Free Tier)
        preferences = [
            'models/gemini-1.5-flash',
            'models/gemini-1.5-flash-001',
            'models/gemini-1.5-pro',
            'models/gemini-pro'
        ]
        
        for p in preferences:
            if p in valid_models:
                return p
        
        return valid_models[0] # Fallback
    except:
        return None

# --- 3. DATA ENGINES ---
def get_financials(ticker):
    try:
        t = ticker.upper().strip().replace(" ", "")
        if not t.endswith(".NS"): t += ".NS"
        
        stock = yf.Ticker(t)
        fin = stock.financials
        bs = stock.balance_sheet
        
        if fin.empty: return None, f"❌ No data for {t}"
        
        years = fin.columns[:3]
        data = {}
        for date in years:
            yr = date.strftime('%Y')
            try:
                rev = fin.loc['Total Revenue', date] / 1e7
                pat = fin.loc['Net Income', date] / 1e7
                equity = bs.loc['Stockholders Equity', date] if 'Stockholders Equity' in bs.index else 1
                
                data[yr] = {
                    "Rev(Cr)": round(rev,0), 
                    "PAT(Cr)": round(pat,0), 
                    "ROE%": round((pat*1e7/equity)*100, 1)
                }
            except: continue
            
        return pd.DataFrame(data).to_markdown(), None
    except Exception as e: return None, str(e)

def get_news(ticker):
    try:
        results = tavily.search(query=f"{ticker} share news india frauds analysis", max_results=3)
        return "\n".join([f"- {r['title']}: {r['content'][:250]}..." for r in results['results']])
    except: return "News Error"

# --- 4. AI WRITER WITH AUTO-RETRY ---
# This decorator automatically retries if it hits a 429 error
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def generate_content_with_retry(model_name, prompt):
    model = genai.GenerativeModel(model_name)
    return model.generate_content(prompt)

# --- 5. MAIN UI ---
ticker_list = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ITC", "SBIN", "TATAMOTORS", "ZOMATO", "M&M"] 
col1, col2 = st.columns([3, 1])

with col1:
    selected_ticker = st.selectbox("Select Company:", sorted(ticker_list), index=None, placeholder="Select stock...")

with col2:
    st.write("") 
    st.write("")
    generate_btn = st.button("🚀 Run Research", type="primary")

if generate_btn:
    if not selected_ticker:
        st.error("Please select a ticker.")
    else:
        with st.spinner("🔍 Connecting to AI..."):
            model_name = get_working_model()
            
            if not model_name:
                st.error("❌ API Error: No working models.")
            else:
                with st.spinner(f"📊 Analyzing {selected_ticker} using {model_name}..."):
                    fin_markdown, error = get_financials(selected_ticker)
                    news_text = get_news(selected_ticker)
                    
                    if error:
                        st.error(error)
                    else:
                        with st.spinner("✍️ Writing Final Report..."):
                            prompt = f"""
                            You are a Senior Analyst. Write a report for **{selected_ticker}**.
                            
                            [DATA]
                            {fin_markdown}
                            
                            [NEWS]
                            {news_text}
                            
                            Output:
                            1. Business Summary
                            2. Financial Trend Analysis
                            3. Risk Flags
                            4. Investment Verdict (Buy/Sell/Hold)
                            """
                            
                            try:
                                # Use the retry function here
                                response = generate_content_with_retry(model_name, prompt)
                                st.markdown("---")
                                st.subheader(f"📝 Report: {selected_ticker}")
                                st.markdown(response.text)
                            except Exception as e:
                                st.error(f"AI Limit Hit: {e}")
                                st.info("💡 Tip: You hit the free tier limit. Wait 60 seconds and try again.")
