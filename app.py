import streamlit as st
import google.generativeai as genai
from tavily import TavilyClient
import yfinance as yf
import pandas as pd
import time

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="AI Equity Researcher", page_icon="📈", layout="wide")

st.title("📈 Agentic Equity Research Assistant")
st.markdown("Generates a professional 19-Point Investment Report using **Live Financials** + **Web Search**.")

# --- SIDEBAR: API KEYS ---
with st.sidebar:
    st.header("🔑 API Configuration")
    st.markdown("Get your free keys: [Google Gemini](https://aistudio.google.com/) | [Tavily](https://tavily.com/)")
    
    # Securely ask for keys
    GOOGLE_API_KEY = st.text_input("Gemini API Key", type="password")
    TAVILY_API_KEY = st.text_input("Tavily API Key", type="password")
    
    st.divider()
    st.markdown("Created with Python & Streamlit")

# --- 1. ROBUST MODEL SELECTOR ---
def get_working_model(api_key):
    """
    Connects to Google and finds the best available model for the user's key.
    Prevents 404 errors.
    """
    genai.configure(api_key=api_key)
    try:
        models = list(genai.list_models())
        valid_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
        
        if not valid_models:
            return None, "No text models found for this key."
            
        # Preference list
        preferences = [
            'models/gemini-1.5-flash',
            'models/gemini-1.5-flash-latest',
            'models/gemini-1.5-pro', 
            'models/gemini-1.0-pro', 
            'models/gemini-pro'
        ]
        
        for p in preferences:
            if p in valid_models:
                return p, None
        
        return valid_models[0], None # Fallback
        
    except Exception as e:
        return None, str(e)

# --- 2. DATA ENGINES ---
def get_financials(ticker):
    """Fetches data from Yahoo Finance"""
    try:
        t = ticker.replace(" ", "").upper() + ".NS"
        stock = yf.Ticker(t)
        fin = stock.financials
        bs = stock.balance_sheet
        
        if fin.empty: return "Data Unavailable", None
        
        # Extract last 3 years for brevity in prompt
        years = fin.columns[:3]
        data = {}
        for date in years:
            yr = date.strftime('%Y')
            try:
                rev = fin.loc['Total Revenue', date] / 1e7
                pat = fin.loc['Net Income', date] / 1e7
                equity = bs.loc['Stockholders Equity', date]
                data[yr] = {
                    "Rev(Cr)": round(rev,0), 
                    "PAT(Cr)": round(pat,0),
                    "ROE%": round((pat*1e7/equity)*100, 1)
                }
            except: pass
            
        df = pd.DataFrame(data)
        return df.to_markdown(), df
    except Exception as e:
        return f"Error: {e}", None

def get_news(ticker, api_key):
    """Fetches news from Tavily"""
    try:
        tavily = TavilyClient(api_key=api_key)
        results = tavily.search(query=f"{ticker} india share news frauds controversy", max_results=3)
        context = ""
        for r in results['results']:
            context += f"- {r['title']}: {r['content'][:200]}...\n"
        return context
    except Exception as e:
        return f"Search Error: {e}"

# --- 3. MAIN APP LOGIC ---

ticker_input = st.text_input("Enter NSE Ticker (e.g. TCS, ZOMATO, RELIANCE):", "").upper()
generate_btn = st.button("🚀 Generate Research Report")

if generate_btn:
    if not GOOGLE_API_KEY or not TAVILY_API_KEY:
        st.error("❌ Please enter both API Keys in the sidebar to proceed.")
    elif not ticker_input:
        st.warning("⚠️ Please enter a ticker symbol.")
    else:
        # --- PHASE 1: DIAGNOSTICS ---
        status_text = st.empty()
        status_text.info("🔍 Checking API connectivity...")
        
        model_name, error = get_working_model(GOOGLE_API_KEY)
        
        if error:
            st.error(f"❌ Connection Failed: {error}")
        else:
            st.success(f"✅ Connected to AI Model: `{model_name}`")
            
            # --- PHASE 2: DATA GATHERING ---
            with st.spinner(f"📊 Fetching Financials & News for {ticker_input}..."):
                fin_markdown, fin_df = get_financials(ticker_input)
                news_text = get_news(ticker_input, TAVILY_API_KEY)
                
                # Show raw data preview (optional)
                with st.expander("View Raw Data Source"):
                    st.subheader("Financials")
                    st.text(fin_markdown)
                    st.subheader("News Context")
                    st.text(news_text)

            # --- PHASE 3: AI WRITING ---
            with st.spinner("✍️ Analyst is writing the report (this takes 10-15s)..."):
                prompt = f"""
                You are a Senior Equity Analyst. Write a structured investment report for **{ticker_input}**.
                
                [REAL DATA SOURCE]
                {fin_markdown}
                
                [NEWS SOURCE]
                {news_text}
                
                ---
                YOUR TASK:
                Write a report covering:
                1. **Executive Summary**: What does the company do? (Brief)
                2. **Financial Health**: Analyze the revenue and ROE trends from the data above.
                3. **Risk Analysis**: Summarize any red flags from the news.
                4. **Investment Verdict**: Buy/Sell/Hold rating with 3 bullet points rationale.
                
                Format with clean Markdown headers and bullet points.
                """
                
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt)
                    report_text = response.text
                    
                    # Display Report
                    st.markdown("---")
                    st.markdown(report_text)
                    
                    # Download Button
                    st.download_button(
                        label="📥 Download Report as Text",
                        data=report_text,
                        file_name=f"{ticker_input}_Research_Report.md",
                        mime="text/markdown"
                    )
                    
                except Exception as e:
                    st.error(f"AI Generation Error: {e}")
            
            status_text.empty() # Clear status