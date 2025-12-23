import streamlit as st
import google.generativeai as genai
from tavily import TavilyClient
import yfinance as yf
import pandas as pd

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="AI Equity Researcher",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Agentic Equity Research Assistant")
st.markdown("Generates a professional Investment Report using **Live Financials** (Yahoo Finance) + **Web Search** (Tavily).")

# --- STEP 1: SMART AUTHENTICATION ---
def load_api_keys():
    """
    Prioritizes Streamlit Secrets. Falls back to Sidebar Manual Input.
    """
    # 1. Try Loading from Secrets (Cloud / Local .streamlit/secrets.toml)
    try:
        g_key = st.secrets["GOOGLE_API_KEY"]
        t_key = st.secrets["TAVILY_API_KEY"]
        return g_key, t_key, "✅ Authenticated via Secrets"
    except (FileNotFoundError, KeyError):
        pass

    # 2. Fallback: Ask User in Sidebar
    with st.sidebar:
        st.header("🔐 Authentication")
        st.caption("Enter keys to proceed (or add them to Secrets for auto-login).")
        g_input = st.text_input("Gemini API Key", type="password")
        t_input = st.text_input("Tavily API Key", type="password")
        
        if not g_input or not t_input:
            return None, None, "⚠️ Waiting for Keys..."
        
        return g_input, t_input, "✅ Authenticated via Sidebar"

# Load Keys
GOOGLE_API_KEY, TAVILY_API_KEY, status_msg = load_api_keys()

# Display Status
if "✅" in status_msg:
    st.success(status_msg)
else:
    st.warning(status_msg)
    st.stop() # Stop execution here until keys are provided

# Configure Clients
genai.configure(api_key=GOOGLE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# --- STEP 2: ROBUST MODEL SELECTOR ---
def get_working_model():
    """
    Finds a valid Gemini model for your API key to prevent 404 Errors.
    """
    try:
        models = list(genai.list_models())
        valid_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
        
        if not valid_models:
            return None
        
        # Preference Order (Fastest -> Strongest)
        preferences = [
            'models/gemini-1.5-flash', 
            'models/gemini-1.5-flash-latest',
            'models/gemini-1.5-pro',
            'models/gemini-pro'
        ]
        
        for p in preferences:
            if p in valid_models:
                return p
        
        return valid_models[0] # Fallback
    except:
        return None

# --- STEP 3: DATA ENGINES ---
def get_financials(ticker):
    """
    Fetches 3-Year Financials from Yahoo Finance with Error Handling.
    """
    try:
        # 1. Clean Ticker
        t = ticker.upper().strip().replace(" ", "")
        if not t.endswith(".NS"):
            t += ".NS"
            
        stock = yf.Ticker(t)
        
        # 2. Fetch Data
        try:
            fin = stock.financials
        except Exception:
            return None, f"Could not connect to Yahoo Finance for {t}"
            
        if fin.empty:
            return None, f"❌ No financial data found for '{t}'. Check if the ticker is correct."
        
        # 3. Process Data
        years = fin.columns[:3]
        data = {}
        for date in years:
            yr = date.strftime('%Y')
            try:
                # Metrics
                rev = fin.loc['Total Revenue', date] / 1e7
                pat = fin.loc['Net Income', date] / 1e7
                
                # Equity (Handle missing BS data)
                equity = 1
                if not stock.balance_sheet.empty and 'Stockholders Equity' in stock.balance_sheet.index:
                     if date in stock.balance_sheet.columns:
                        equity = stock.balance_sheet.loc['Stockholders Equity', date]

                roe = (pat * 1e7 / equity) * 100
                
                data[yr] = {
                    "Revenue(Cr)": round(rev, 0),
                    "PAT(Cr)": round(pat, 0),
                    "ROE %": round(roe, 1)
                }
            except:
                continue

        if not data:
            return None, "❌ Data found but could not parse Revenue/Profit."

        return pd.DataFrame(data).to_markdown(), None

    except Exception as e:
        return None, f"Critical Error: {str(e)}"

def get_news(ticker):
    """
    Fetches news summaries from Tavily.
    """
    try:
        query = f"{ticker} share price news india frauds analysis"
        results = tavily.search(query=query, max_results=3)
        context = ""
        for r in results['results']:
            context += f"- {r['title']}: {r['content'][:250]}...\n"
        return context
    except Exception as e:
        return f"News Error: {str(e)}"

# --- STEP 4: MAIN UI & EXECUTION ---
ticker_input = st.text_input("Enter NSE Ticker Symbol (e.g. ZOMATO, RELIANCE, TCS):", "").upper()
generate_btn = st.button("🚀 Generate Research Report")

if generate_btn:
    if not ticker_input:
        st.error("Please enter a ticker symbol.")
    else:
        # 1. Connection Check
        with st.spinner("🔍 Connecting to AI Brain..."):
            model_name = get_working_model()
            
        if not model_name:
            st.error("❌ API Error: No working Gemini models found for your key.")
        else:
            # 2. Data Gathering
            with st.spinner(f"📊 Gathering Financials & News for {ticker_input}..."):
                fin_markdown, error_msg = get_financials(ticker_input)
                news_text = get_news(ticker_input)
                
                if error_msg:
                    st.error(error_msg)
                else:
                    # 3. Show Raw Data (Optional Transparency)
                    with st.expander("View Source Data"):
                        st.subheader("Financials")
                        st.text(fin_markdown)
                        st.subheader("News Context")
                        st.text(news_text)
                    
                    # 4. AI Synthesis
                    with st.spinner("✍️ Analyst is writing the report..."):
                        prompt = f"""
                        You are a Senior Equity Research Analyst.
                        Write a professional investment report for **{ticker_input}**.
                        
                        [REAL DATA SOURCE]
                        {fin_markdown}
                        
                        [NEWS SOURCE]
                        {news_text}
                        
                        ---
                        YOUR REPORT STRUCTURE:
                        1. **Executive Summary**: What does the company do?
                        2. **Financial Health Check**: Analyze the Revenue and ROE trends from the data above.
                        3. **Risk Analysis**: Summarize any red flags or negative news found.
                        4. **Investment Verdict**: Buy/Sell/Hold rating with specific rationale.
                        
                        Use clear Markdown formatting with bullet points.
                        """
                        
                        try:
                            model = genai.GenerativeModel(model_name)
                            response = model.generate_content(prompt)
                            
                            st.markdown("---")
                            st.subheader(f"📝 Research Report: {ticker_input}")
                            st.markdown(response.text)
                            
                        except Exception as e:
                            st.error(f"AI Generation Failed: {str(e)}")
