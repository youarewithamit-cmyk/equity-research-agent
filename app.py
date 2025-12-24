import streamlit as st
import google.generativeai as genai
from tavily import TavilyClient
import yfinance as yf
import pandas as pd
import time

# --- PAGE CONFIGURATION ---
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

# Configure Clients
genai.configure(api_key=GOOGLE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# --- 2. DYNAMIC MODEL SELECTOR (The 404 Fix) ---
def get_working_model():
    """
    Asks Google which models are allowed for this Key.
    """
    try:
        models = list(genai.list_models())
        
        # Filter for models that generate text
        valid_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
        
        if not valid_models:
            return None
        
        # Priority List: Try to get the best one that exists in the valid list
        # We prefer Flash (fast/free) -> Pro (smart) -> Standard
        priority = [
            'models/gemini-1.5-flash', 
            'models/gemini-1.5-flash-latest',
            'models/gemini-1.5-pro',
            'models/gemini-pro',
            'models/gemini-1.0-pro'
        ]
        
        for p in priority:
            if p in valid_models:
                return p
        
        # If none of our favorites exist, just take the first valid one we found
        return valid_models[0] 
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
    except: return "News unavailable."

# --- 4. SAFE GENERATOR (Uses Detected Model) ---
def generate_report_safe(model_name, prompt):
    # CRITICAL FIX: Use the model_name passed in, NOT a hardcoded string
    model = genai.GenerativeModel(model_name)
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        error_str = str(e)
        if "429" in error_str:
            st.warning("⏳ Free Tier Limit Hit. Retrying in 20 seconds...")
            time.sleep(20)
            try:
                response = model.generate_content(prompt)
                return response.text
            except:
                return "❌ Error: Quota exceeded. Please try again in 1 minute."
        else:
            return f"Error: {e}"

# --- 5. MAIN UI ---
ticker_list = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "ITC", "BHARTIARTL",
    "SBIN", "LICI", "HINDUNILVR", "TATAMOTORS", "LT", "BAJFINANCE", "HCLTECH",
    "MARUTI", "SUNPHARMA", "ADANIENT", "TITAN", "KOTAKBANK", "ONGC", "TATASTEEL",
    "NTPC", "POWERGRID", "ASIANPAINT", "ULTRACEMCO", "AXISBANK", "WIPRO", "M&M",
    "ZOMATO", "DMART", "HAL", "BEL", "TRENT", "COALINDIA", "SIEMENS", "INDIGO"
]

col1, col2 = st.columns([3, 1])
with col1:
    selected_ticker = st.selectbox("Select Company:", sorted(ticker_list), index=None, placeholder="Type to search...")
with col2:
    st.write("") 
    st.write("")
    generate_btn = st.button("🚀 Run Research", type="primary")

if generate_btn:
    if not selected_ticker:
        st.error("Please select a ticker.")
    else:
        # 1. Detect Model First
        with st.spinner("🔍 Connecting to AI..."):
            valid_model_name = get_working_model()
            
        if not valid_model_name:
            st.error("❌ API Error: No text models found for your API Key.")
        else:
            # 2. Run Analysis
            with st.spinner(f"📊 Analyzing {selected_ticker} using {valid_model_name}..."):
                fin_markdown, error = get_financials(selected_ticker)
                news_text = get_news(selected_ticker)
                
                if error:
                    st.error(error)
                else:
                    with st.spinner("✍️ Writing Report..."):
                        prompt = f"""
                        You are a Senior Analyst. Write a report for **{selected_ticker}**.
                        
                        [DATA]
                        {fin_markdown}
                        
                        [NEWS]
                        {news_text}
                        
                        Output Structure:
                        1. **Business Summary**
                        2. **Financial Trend Analysis**
                        3. **Risk Analysis**
                        4. **Investment Verdict**
                        """
                        
                        # Pass the VALID model name to the generator
                        report = generate_report_safe(valid_model_name, prompt)
                        
                        if "Error" in report:
                            st.error(report)
                        else:
                            st.markdown("---")
                            st.subheader(f"📝 Research Report: {selected_ticker}")
                            st.markdown(report)
