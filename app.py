import streamlit as st
import google.generativeai as genai
from tavily import TavilyClient
import yfinance as yf
import pandas as pd
import time
from tenacity import retry, stop_after_attempt, wait_fixed

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
    """
    Prioritizes Streamlit Secrets. Falls back to Sidebar Manual Input.
    """
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
    st.stop() # Stop execution until keys are present

# Configure Clients
genai.configure(api_key=GOOGLE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# --- 2. DATA ENGINES ---
def get_financials(ticker):
    """
    Fetches 3-Year Financials from Yahoo Finance with Error Handling.
    """
    try:
        # Smart Ticker Cleaning
        t = ticker.upper().strip().replace(" ", "")
        if not t.endswith(".NS"): 
            t += ".NS"
        
        stock = yf.Ticker(t)
        fin = stock.financials
        bs = stock.balance_sheet
        
        if fin.empty: 
            return None, f"❌ No data found for '{t}'. Check if the ticker is correct."
        
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
            except: 
                continue
            
        return pd.DataFrame(data).to_markdown(), None
    except Exception as e: 
        return None, str(e)

def get_news(ticker):
    """
    Fetches news summaries from Tavily.
    """
    try:
        results = tavily.search(query=f"{ticker} share news india frauds analysis", max_results=3)
        return "\n".join([f"- {r['title']}: {r['content'][:250]}..." for r in results['results']])
    except: 
        return "News unavailable."

# --- 3. ROBUST AI GENERATION ---
# Forced to use 'gemini-1.5-flash' (1500 RPD) to avoid '429 Quota' errors.
def generate_report_safe(prompt):
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        error_str = str(e)
        if "429" in error_str:
            st.warning("⏳ Google Free Tier Limit Hit. Cooling down for 30 seconds...")
            time.sleep(30)
            try:
                # One retry after waiting
                response = model.generate_content(prompt)
                return response.text
            except:
                return "❌ Error: Quota exceeded. Please try again in 1 minute."
        else:
            return f"Error: {e}"

# --- 4. MAIN UI ---
# Searchable Dropdown List
ticker_list = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "ITC", "BHARTIARTL",
    "SBIN", "LICI", "HINDUNILVR", "TATAMOTORS", "LT", "BAJFINANCE", "HCLTECH",
    "MARUTI", "SUNPHARMA", "ADANIENT", "TITAN", "KOTAKBANK", "ONGC", "TATASTEEL",
    "NTPC", "POWERGRID", "ASIANPAINT", "ULTRACEMCO", "AXISBANK", "WIPRO", "M&M",
    "ZOMATO", "DMART", "HAL", "BEL", "TRENT", "COALINDIA", "SIEMENS", "INDIGO"
]

col1, col2 = st.columns([3, 1])

with col1:
    selected_ticker = st.selectbox(
        "Select Company:", 
        sorted(ticker_list), 
        index=None, 
        placeholder="Type to search..."
    )

with col2:
    st.write("") # Spacers
    st.write("")
    generate_btn = st.button("🚀 Run Research", type="primary")

# --- 5. EXECUTION LOGIC ---
if generate_btn:
    if not selected_ticker:
        st.error("Please select a ticker from the dropdown.")
    else:
        with st.spinner(f"📊 Analyzing {selected_ticker}..."):
            # 1. Fetch Data
            fin_markdown, error = get_financials(selected_ticker)
            news_text = get_news(selected_ticker)
            
            if error:
                st.error(error)
            else:
                # 2. Write Report
                with st.spinner("✍️ Analyst is writing the report..."):
                    prompt = f"""
                    You are a Senior Analyst. Write a report for **{selected_ticker}**.
                    
                    [DATA]
                    {fin_markdown}
                    
                    [NEWS]
                    {news_text}
                    
                    Output Structure:
                    1. **Business Summary**: Brief description.
                    2. **Financial Trend Analysis**: Comment on Revenue and ROE growth.
                    3. **Risk Analysis**: Any red flags from news?
                    4. **Investment Verdict**: Buy/Sell/Hold rating with rationale.
                    """
                    
                    report = generate_report_safe(prompt)
                    
                    if "Error" in report:
                        st.error(report)
                    else:
                        st.markdown("---")
                        st.subheader(f"📝 Research Report: {selected_ticker}")
                        st.markdown(report)
