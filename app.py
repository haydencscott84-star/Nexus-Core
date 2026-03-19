import streamlit as st
import pandas as pd
import altair as alt
import os
from dotenv import load_dotenv
import google.generativeai as genai
from streamlit_autorefresh import st_autorefresh

# Import global Supabase caching from the later section of the file
# Or recreate it here if it's currently defined at the bottom
from supabase import create_client, Client

# Import global Supabase caching from the later section of the file
from supabase import create_client, Client

# Load Environment Variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize Supabase client globally so all tables can use it
@st.cache_resource
def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("Missing Supabase credentials in .env")
    return create_client(url, key)

import datetime

# Broad Market Streamer Component
@st.fragment(run_every="5s")
def render_broad_market_streamer():
    client = get_supabase_client()
    if not client: return
    
    try:
        res = client.table("nexus_profile").select("data").eq("id", "broad_market").execute()
        
        # Prepare fallback data
        data = {}
        prices = {}
        if res.data and len(res.data) > 0:
            data = res.data[0]["data"]
            prices = data.get("prices", {})
        
        # Show update time
        updated_ts = data.get("updated_at", 0)
        dt_str = datetime.datetime.fromtimestamp(updated_ts).strftime('%H:%M:%S ET') if updated_ts else "Waiting for Initial Tick..."

        st.markdown(f"### 📈 Broad Market Live <span style='font-size: 14px; color: #a0a0a0; font-weight: normal; margin-left: 15px;'>Last tick: {dt_str}</span>", unsafe_allow_html=True)
        
        # ROW 1 (Indices & Futures)
        row1_cols = st.columns(6)
        
        spy_data = prices.get("SPY", {})
        spx_data = prices.get("$SPX.X", {})
        vix_data = prices.get("$VIX.X", {})
        es_data = prices.get("@ES", {})
        nq_data = prices.get("@NQ", {})
        iwm_data = prices.get("IWM", {}) # Added IWM data fetch
        mesh_data = prices.get("MESM26", {}) # Changed from MESM26 to MESM26
        
        # Display Row 1
        with row1_cols[0]: st.metric("SPY", f"{spy_data.get('curr', 0):.2f}", f"{spy_data.get('chg_pct', 0):+.2f}%")
        with row1_cols[1]: st.metric("SPX", f"{spx_data.get('curr', 0):.2f}", f"{spx_data.get('chg_pct', 0):+.2f}%")
        with row1_cols[2]: st.metric("VIX", f"{vix_data.get('curr', 0):.2f}", f"{vix_data.get('chg_pct', 0):+.2f}%", delta_color="inverse")
        with row1_cols[3]: st.metric("S&P 500 (@ES)", f"{es_data.get('curr', 0):.2f}", f"{es_data.get('chg_pct', 0):+.2f}%")
        with row1_cols[4]: st.metric("Nasdaq (@NQ)", f"{nq_data.get('curr', 0):.2f}", f"{nq_data.get('chg_pct', 0):+.2f}%")
        with row1_cols[5]: st.metric("Micro ES (MESM26)", f"{mesh_data.get('curr', 0):.2f}", f"{mesh_data.get('chg_pct', 0):+.2f}%")

        # ROW 2 (Sectors)
        sectors = ["XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLC", "XLI", "XLB", "XLRE", "XLU"]
        row2_cols = st.columns(len(sectors))
        for i, sector in enumerate(sectors):
            s_data = prices.get(sector, {})
            with row2_cols[i]: st.metric(sector, f"{s_data.get('curr', 0):.2f}", f"{s_data.get('chg_pct', 0):+.2f}%")
        
        st.divider()

    except Exception as e:
        st.error(f"Failed to load Broad Market Streamer: {str(e)}")

# 1. Page Configuration
st.set_page_config(page_title="Market Regime & Options Flow", layout="wide")

# =====================================================================
# SECURE GATEWAY
# =====================================================================
MASTER_PASSWORD = "mastersound"
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    # Display logo and password input
    _, col_login, _ = st.columns([1, 2, 1])
    with col_login:
        st.markdown("<h1 style='text-align: center;'>🔒 Nexus Core</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: gray;'>Institutional System Authentication Required</p>", unsafe_allow_html=True)
        pwd = st.text_input("Enter Master Password", type="password")
        if pwd:
            if pwd == MASTER_PASSWORD:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Access Denied.")
    st.stop()

import json
import datetime

@st.cache_data(ttl=30)
def load_nexus_spy_profile():
    client = get_supabase_client()
    if client:
        try:
            res = client.table("nexus_profile").select("data").eq("id", "spy_latest").execute()
            if res.data and len(res.data) > 0:
                return res.data[0]["data"]
        except Exception as e:
            print(f"Fetch error: {e}")
            
    # Fallback to local
    try:
        with open('/Users/haydenscott/Desktop/Local Scripts/nexus_spy_profile.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        return {}

@st.cache_data(ttl=30)
def load_nexus_profile():
    client = get_supabase_client()
    if client:
        try:
            res = client.table("nexus_profile").select("data").eq("id", "latest").execute()
            if res.data and len(res.data) > 0:
                return res.data[0]["data"]
        except Exception as e:
            print(f"Fetch error: {e}")
            
    # Fallback to local
    try:
        with open('/Users/haydenscott/Desktop/Local Scripts/nexus_spx_profile.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        return {}

@st.cache_data(ttl=30)
def load_nexus_history():
    client = get_supabase_client()
    if client:
        try:
            res = client.table("nexus_profile").select("data").eq("id", "nexus_history").execute()
            if res.data and len(res.data) > 0:
                return res.data[0]["data"]
        except Exception as e:
            print(f"Fetch error: {e}")
            
    # Fallback to local
    try:
        with open('/Users/haydenscott/Desktop/Local Scripts/nexus_history.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        return {}
@st.cache_data(ttl=30)
def load_mtf_nexus():
    client = get_supabase_client()
    if client:
        try:
            res = client.table("nexus_profile").select("data").eq("id", "mtf_latest").execute()
            if res.data and len(res.data) > 0:
                return res.data[0]["data"]
        except Exception as e:
            print(f"Fetch error: {e}")
            
    # Fallback to local
    try:
        with open('/Users/haydenscott/Desktop/Local Scripts/nexus_mtf_data.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        return {}
        
@st.cache_data(ttl=30)
def load_nexus_quant():
    client = get_supabase_client()
    if client:
        try:
            res = client.table("nexus_profile").select("data").eq("id", "nexus_quant").execute()
            if res.data and len(res.data) > 0:
                return res.data[0]["data"]
        except Exception as e:
            print(f"Fetch error: {e}")
            
    # Fallback to local
    try:
        with open('/Users/haydenscott/Desktop/Local Scripts/nexus_quant.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        return {}

@st.cache_data(ttl=60)
def load_oi_book():
    client = get_supabase_client()
    if client:
        try:
            res = client.table("nexus_profile").select("data").eq("id", "oi_book").execute()
            if res.data and len(res.data) > 0:
                return res.data[0]["data"]
        except Exception as e:
            print(f"Fetch error: {e}")
    return {}

# Run the dashboard automatically every 1 minute (60000 milliseconds)
if st.session_state.get('run_gemini', False):
    count = st_autorefresh(interval=9999999, limit=None, key="data_refresh_paused")
else:
    count = st_autorefresh(interval=60000, limit=None, key="data_refresh")

st.title("Market Regime & Options Flow")

# Mount Broad Market Fragment
render_broad_market_streamer()

import json
import datetime

# AI Inference Engine
def generate_market_rundown(spy_top5_str, spx_top5_str, regime_str, spy_prof_str, spx_prof_str):
    if not GEMINI_API_KEY:
        return "⚠️ Error: GEMINI_API_KEY not found in local .env"
    
    prompt = f"""
Act as an elite quantitative options flow analyst. Below is the live Options flow and current Market Regime status.

YOUR CONSTITUTION:
1. Style: INSTITUTIONAL_SWING (Strict 7-Day Horizon).
2. Philosophy: "Don't fight the trend, but respect the structure. Volatility is opportunity, not just risk. We analyze the convergence of BOTH SPX Structure and SPY Flow to determine institutional intent and market direction."
3. Output rules: Be highly precise and moderately concise. Do not write filler paragraphs. Focus entirely on predicting the 7-day structural trajectory. Connect the volume POC (Magnet), underlying Support/Resistance, and massive institutional shifts. Conclude with actionable directional probabilities for the week.
4. CRITICAL FORMATTING: NEVER use the '$' symbol anywhere in your response. Streamlit interprets '$' as LaTeX math blocks, which breaks and italicizes all the text. Use 'USD' or just write the raw number.

--- LATEST MARKET REGIME & MACRO CONTEXT ---
{regime_str}

--- SPY PROFILER CONTEXT (Net Flow, Gamma, Walls) ---
{spy_prof_str}

--- SPX PROFILER CONTEXT (Support/Resistance Walls) ---
{spx_prof_str}

--- TOP 5 SPY SHIFTS (Δ OI) ---
{spy_top5_str}

--- TOP 5 SPX SHIFTS (Δ OI) ---
{spx_top5_str}

Format your output EXACTLY as follows:
**Institutional Positioning:** (Concise bullet points on how the massive OI shifts are restructuring the 7-day floor/ceiling)
**Structural Mechanics (SPX & SPY):** (Crisp breakdown of Call/Put walls, Gamma regimes, and the Magnet's gravitational pull)
**Actionable 7-Day Trajectory:** (Punchy, definitive strategic conclusion for the next 7 days, explicitly outlining the highest probability path of least resistance and key invalidation levels)
"""
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt, stream=True)
        for chunk in response:
            yield chunk.text
    except Exception as e:
        import traceback
        yield f"⚠️ API Connection Error: {str(e)}\n\n{traceback.format_exc()}"

# 2. Data Loading Engine
@st.cache_data(ttl=30)
def fetch_and_calculate_data():
    try:
        supabase = get_supabase_client()
        
        # 1. Fetch Market Regime (Dual-Written from remote_nexus_sheets_bridge.py)
        res_regime = supabase.table("nexus_profile").select("data").eq("id", "market_regime").execute()
        if len(res_regime.data) > 0 and 'data' in res_regime.data[0]:
            r_data = res_regime.data[0]['data']
            df_regime = pd.DataFrame(r_data.get('rows', []), columns=r_data.get('headers', []))
        else:
            df_regime = pd.DataFrame()
            
        # 2. Fetch SPX Ledger (Dual-Written from update_ledger_sheet.py)
        res_spx = supabase.table("nexus_profile").select("data").eq("id", "spx_flow_ledger").execute()
        if len(res_spx.data) > 0 and 'data' in res_spx.data[0]:
            s_data = res_spx.data[0]['data']
            df_spx_vol = pd.DataFrame(s_data.get('top_vol', []))
            df_spx_oi = pd.DataFrame(s_data.get('top_oi', []))
            st.session_state['spx_update_time'] = s_data.get('last_updated', 'Pending EOD Sync...')
        else:
            df_spx_vol, df_spx_oi = pd.DataFrame(), pd.DataFrame()
            st.session_state['spx_update_time'] = 'Pending EOD Sync...'
            
        # 3. Fetch SPY Ledger (Dual-Written from spy_ledger_sheet.py)
        res_spy = supabase.table("nexus_profile").select("data").eq("id", "spy_flow_ledger").execute()
        if len(res_spy.data) > 0 and 'data' in res_spy.data[0]:
            py_data = res_spy.data[0]['data']
            df_spy_vol = pd.DataFrame(py_data.get('top_vol', []))
            df_spy_oi = pd.DataFrame(py_data.get('top_oi', []))
            st.session_state['spy_update_time'] = py_data.get('last_updated', 'Pending EOD Sync...')
        else:
            df_spy_vol, df_spy_oi = pd.DataFrame(), pd.DataFrame()
            st.session_state['spy_update_time'] = 'Pending EOD Sync...'

    except Exception as e:
        print(f"Failed to fetch from Supabase: {e}")
        # Return empty dataframes to prevent crash
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        
    # Clean up empty NaN cells into blank strings for cleaner display
    df_spy_vol = df_spy_vol.fillna("")
    df_spy_oi = df_spy_oi.fillna("")
    df_spx_vol = df_spx_vol.fillna("")
    df_spx_oi = df_spx_oi.fillna("")
    
    # Cast flow metrics to numeric for Streamlit Styler formatting
    flow_numeric_cols = ['Total Volume', 'Start OI', 'End OI', 'Δ OI', 'Vol/OI', 'RVOL', 'Δ² OI', 'Strike']
    for df in [df_spy_vol, df_spy_oi, df_spx_vol, df_spx_oi]:
        if not df.empty:
            for col in flow_numeric_cols:
                if col in df.columns:
                    # Remove commas and $ before casting
                    clean_str = df[col].astype(str).str.replace(r'[\$,]', '', regex=True)
                    # Convert to numeric, errors='coerce' turns unparseable strings back into NaN
                    df[col] = pd.to_numeric(clean_str, errors='coerce')
    
    # Strip invisible trailing spaces from Google Sheets headers (e.g. "VIX ")
    if not df_regime.empty:
        df_regime.columns = df_regime.columns.str.strip()
        
        # Cast SPX / SPY price columns to float in case Google Sheets exports them as strings
        numeric_cols = [
            'Current SPY $', 'Current SPX $', 
            'VIX', 'VIX curve', 
            'HRLY RVOL SPY', 'HRLY RVOL SPX', 
            'Force Index - 2-EMA', 'Force Index - 13-EMA', 
            'Trend Strength'
        ]
        for col in numeric_cols:
            if col in df_regime.columns:
                # Split by space and take the first part to remove trailing text like " ($687.99)"
                clean_str = df_regime[col].astype(str).str.split().str[0].str.replace(r'[\$,]', '', regex=True)
                df_regime[col] = pd.to_numeric(clean_str, errors='coerce')
                
        # Remove any row where the 'Session' column contains "START UP" or "Loop"
        if 'Session' in df_regime.columns:
            df_regime = df_regime[~df_regime['Session'].astype(str).str.contains('START UP|Loop', case=False, na=False)]
            
    # Reorder columns to exactly match the legacy Google Sheets layout
    target_columns = [
        'Strike', 'Type', 'Top Expiration', 'Total Volume', 
        'Start OI', 'End OI', 'Δ OI', 'Vol/OI', 'RVOL', 'Δ² OI', 
        'Dist %', 'Sentiment'
    ]
    
    if not df_spy_vol.empty: df_spy_vol = df_spy_vol[[c for c in target_columns if c in df_spy_vol.columns]]
    if not df_spy_oi.empty:  df_spy_oi  = df_spy_oi[[c for c in target_columns if c in df_spy_oi.columns]]
    if not df_spx_vol.empty: df_spx_vol = df_spx_vol[[c for c in target_columns if c in df_spx_vol.columns]]
    if not df_spx_oi.empty:  df_spx_oi  = df_spx_oi[[c for c in target_columns if c in df_spx_oi.columns]]
    
    return df_regime, df_spy_vol, df_spy_oi, df_spx_vol, df_spx_oi

# 3. Execution
df_regime, df_spy_vol, df_spy_oi, df_spx_vol, df_spx_oi = fetch_and_calculate_data()

# Custom Logic to color the rows based on the Sentiment text
def style_sentiment(row):
    color = 'font-size: 15px;'
    sentiment_val = str(row.get('Sentiment', ''))
    
    if 'Bullish' in sentiment_val:
        color += ' background-color: rgba(38, 166, 91, 0.15);' # Light green tint
    elif 'Bearish' in sentiment_val:
        color += ' background-color: rgba(231, 76, 60, 0.15);' # Light red tint
        
    return [color] * len(row)

# Custom Logic to dynamically color Call/Put Walls based on price changes
def style_wall(s):
    # s is a pandas Series in reversed chronological order (newest first).
    # We must iterate backwards (oldest to newest) to calculate the price delta.
    import re
    colors = []
    prev_val = None
    prev_color = ''
    
    for val in s[::-1]: # oldest -> newest
        color = ''
        try:
            val_str = str(val)
            # Try to grab the SPY equivalent price first (e.g. [SPY $669.23])
            m_spy = re.search(r'SPY\s*\$?([0-9,]+(?:\.[0-9]+)?)', val_str)
            if m_spy:
                current_val = float(m_spy.group(1).replace(',', ''))
            else:
                # Fallback to the main strike price
                m = re.search(r'\$?([0-9,]+(?:\.[0-9]+)?)', val_str)
                if m:
                    current_val = float(m.group(1).replace(',', ''))
                else:
                    current_val = None
                    
            if current_val is not None:
                if prev_val is None:
                    color = ''
                elif current_val > prev_val:
                    color = 'background-color: rgba(38, 166, 91, 0.15);'
                elif current_val < prev_val:
                    color = 'background-color: rgba(231, 76, 60, 0.15);'
                else:
                    color = prev_color
                
                prev_val = current_val
                prev_color = color if color != '' else prev_color
            else:
                color = prev_color
        except Exception:
            color = prev_color
            
        colors.append(color)
        
    # Reverse the resulting color list to match the newest->oldest DataFrame order
    return colors[::-1]

# Custom logic to color GEX columns
def style_gex(s):
    colors = []
    for val in s:
        val_str = str(val).lower()
        if 'sticky' in val_str or '+' in val_str:
            colors.append('background-color: rgba(38, 166, 91, 0.15);') # Green
        elif 'slippery' in val_str or '-' in val_str:
            colors.append('background-color: rgba(231, 76, 60, 0.15);') # Red
        else:
            colors.append('')
    return colors

# Generic numerical delta styling for Current Price columns
def style_price_delta(s):
    colors = []
    prev_val = None
    prev_color = ''
    
    for val in s[::-1]: # oldest -> newest
        color = ''
        try:
            current_val = float(val) if pd.notnull(val) else None
            
            if current_val is not None:
                if prev_val is None:
                    color = ''
                elif current_val > prev_val:
                    color = 'background-color: rgba(38, 166, 91, 0.15);' # Green
                elif current_val < prev_val:
                    color = 'background-color: rgba(231, 76, 60, 0.15);' # Red
                else:
                    color = prev_color
                
                prev_val = current_val
                prev_color = color if color != '' else prev_color
            else:
                color = prev_color
        except Exception:
            color = prev_color
            
        colors.append(color)
        
    return colors[::-1]

# Set up standard formatting
format_dict = {
    # Flow Ledger Columns
    'Strike': '{:,.0f}',
    'Total Volume': '{:,.0f}',
    'Start OI': '{:,.0f}',
    'End OI': '{:,.0f}',
    'Δ OI': '{:,.0f}',
    'Vol/OI': '{:,.2f}',
    'RVOL': '{:,.2f}',
    'Δ² OI': '{:,.0f}',
    
    # Market Regime Columns
    'Current SPY $': '{:,.2f}',
    'Current SPX $': '{:,.2f}',
    'VIX': '{:,.2f}',
    'VIX curve': '{:,.2f}',
    'HRLY RVOL SPY': '{:,.2f}',
    'HRLY RVOL SPX': '{:,.2f}',
    'Force Index - 2-EMA': '{:,.2f}',
    'Force Index - 13-EMA': '{:,.2f}',
    'Trend Strength': '{:,.2f}'
}

# --- TOP SECTION: GEMINI MARKET RUNDOWN ---
main_tab_mr, main_tab_killbox, main_tab_profiler, main_tab_profiler_spy, main_tab_oi_book, main_tab_mtf = st.tabs(["Market Regime & Options Flow", "Killbox Analysis", "SPX Profiler", "SPY Profiler", "OI Book", "MTF Nexus Analysis"])
with main_tab_mr:
    col1, col2 = st.columns([0.8, 0.2])
    with col1:
        st.header("🧠 Gemini Market Rundown")
    with col2:
        ask_button = st.button("Ask Gemini", use_container_width=True)

    if not GEMINI_API_KEY:
        st.error("Missing GEMINI_API_KEY in .env file.")
    else:
        if ask_button and not st.session_state.get('run_gemini', False):
            st.session_state['run_gemini'] = True
            st.rerun()
            
        if st.session_state.get('run_gemini', False):
            with st.status("🧠 Gemini is analyzing structural flow...", expanded=True):
                # Synthesize top 5 lines into CSV strings to pass to the cacheable AI engine
            
                # Pre-format the timestamps into strict string literals so the LLM doesn't truncate the 'Day'
                df_spy_prompt = df_spy_oi.head(5).copy()
                df_spx_prompt = df_spx_oi.head(5).copy()
            
                for df_p in [df_spy_prompt, df_spx_prompt]:
                    if 'Top Expiration' in df_p.columns:
                        df_p['Top Expiration'] = pd.to_datetime(df_p['Top Expiration']).dt.strftime('%Y-%m-%d')
    
                spy_prompt_data = df_spy_prompt.to_csv(index=False)
                spx_prompt_data = df_spx_prompt.to_csv(index=False)
                regime_prompt_data = df_regime.iloc[::-1].head(1).to_csv(index=False) if not df_regime.empty else "No Regime Data"
                
                # Retrieve the full active Market Profilers and serialize them into clean strings for Gemini Context
                spy_prof = load_nexus_spy_profile() or {}
                if isinstance(spy_prof, str): 
                    try: spy_prof = json.loads(spy_prof)
                    except: spy_prof = {}
                    
                spx_prof = load_nexus_profile() or {}
                if isinstance(spx_prof, str): 
                    try: spx_prof = json.loads(spx_prof)
                    except: spx_prof = {}
                
                # Extract only the high-level structural metrics to prevent Gemini token explosion
                spy_clean = {
                    "current_price": spy_prof.get("current_spy_price"),
                    "magnet": spy_prof.get("magnet"),
                    "zero_gamma": spy_prof.get("zero_gamma"),
                    "net_flow": spy_prof.get("net_gamma"), 
                    "net_delta": spy_prof.get("net_delta"),
                    "futures_implied": spy_prof.get("futures_implied"),
                    "volume_poc": spy_prof.get("vol_poc"),
                    "call_wall": spy_prof.get("call_wall"),
                    "put_wall": spy_prof.get("put_wall")
                }
                
                spx_clean = {
                    "current_price": spx_prof.get("current_spx_price"),
                    "magnet": spx_prof.get("magnet"),
                    "zero_gamma": spx_prof.get("zero_gamma"),
                    "net_gamma": spx_prof.get("net_gamma"),
                    "net_delta": spx_prof.get("net_delta"),
                    "futures_implied": spx_prof.get("futures_implied"),
                    "volume_poc": spx_prof.get("vol_poc"),
                    "call_wall": spx_prof.get("call_wall"),
                    "put_wall": spx_prof.get("put_wall")
                }
                
                spy_prof_str = json.dumps(spy_clean, indent=2)
                spx_prof_str = json.dumps(spx_clean, indent=2)
            
                try:
                    st.session_state['gemini_analysis'] = st.write_stream(generate_market_rundown(spy_prompt_data, spx_prompt_data, regime_prompt_data, spy_prof_str, spx_prof_str))
                    st.session_state['gemini_timestamp'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    st.error("Stream interrupted or failed.")
                finally:
                    st.session_state['run_gemini'] = False
                    st.rerun()
        elif 'gemini_analysis' in st.session_state:
            st.markdown(f"*(Historical Analysis Generated at: {st.session_state['gemini_timestamp']})*")
            st.markdown(st.session_state['gemini_analysis'])
        else:
            st.info("Click 'Ask Gemini' to generate the latest institutional analysis.")
    st.divider()

    # --- MIDDLE SECTION: VISUAL CHARTS ---
    st.header("📊 Market Structure Charts")

    # Extract the most recent Date from the dataframe for the freshness timestamp
    try:
        fresh_date = str(df_regime.iloc[-1]['Date'])
        # Re-format 'YYYY-MM-DD' into 'Month DD, YYYY'
        formatted_date = pd.to_datetime(fresh_date).strftime('%B %d, %Y')
        st.caption(f"**Data Freshness:** T+1 EOD Options Flow. Last Updated: {formatted_date}.")
    except Exception:
        st.caption("**Data Freshness:** T+1 EOD Options Flow.")

    # Helper function to generate standardized Altair bar charts
    def create_flow_chart(df, metric, title):
        # Convert metric columns to float, clean strings
        chart_df = df.copy()
        if chart_df[metric].dtype == object:
            chart_df[metric] = pd.to_numeric(chart_df[metric].astype(str).str.replace(r'[\$,]', '', regex=True), errors='coerce')
    
        # Let Altair handle Strike as a continuous quantitative variable on an ordinal scale, sorted ascending so 
        # strikes run consecutively like an options chain.
        chart_df['Strike'] = pd.to_numeric(chart_df['Strike'], errors='coerce')
    
        chart = alt.Chart(chart_df).mark_bar(opacity=0.8).encode(
            y=alt.Y('Strike:O', sort='descending', title='Strike Price'),
            x=alt.X(f'{metric}:Q', title=metric),
            color=alt.Color('Type:N', scale=alt.Scale(domain=['Call', 'Put'], range=['#2e7d32', '#d32f2f']), legend=alt.Legend(title="Option Type")),
            tooltip=['Strike', 'Type', metric, 'Sentiment']
        ).properties(
            title=title,
            height=600
        ).interactive()
        return chart

    tab_chart_spy, tab_chart_spx = st.tabs(["SPY Wall Structure", "SPX Wall Structure"])

    with tab_chart_spy:
        col1, col2 = st.columns(2)
        with col1:
            st.altair_chart(create_flow_chart(df_spy_vol, 'Total Volume', 'Top SPY Volume Nodes'), use_container_width=True)
        with col2:
            st.altair_chart(create_flow_chart(df_spy_oi, 'Δ OI', 'Largest SPY OI Shifts'), use_container_width=True)

    with tab_chart_spx:
        col1, col2 = st.columns(2)
        with col1:
            st.altair_chart(create_flow_chart(df_spx_vol, 'Total Volume', 'Top SPX Volume Nodes'), use_container_width=True)
        with col2:
            st.altair_chart(create_flow_chart(df_spx_oi, 'Δ OI', 'Largest SPX OI Shifts'), use_container_width=True)

    st.divider()

    # --- BOTTOM SECTION: RAW DATA TABLES ---
    st.header("⚙️ Raw Options Flow Data")

    with st.expander("Hourly Market Updates", expanded=True):
        regime_styled = (
            df_regime.iloc[::-1].style
            .set_properties(**{'font-size': '15px'})
            .apply(style_wall, subset=['Call Wall', 'Put Wall'], axis=0) # Dynamic string delta coloration
            .apply(style_price_delta, subset=['Current SPY $', 'Current SPX $'], axis=0) # Dynamic numerical delta coloration
            .apply(style_gex, subset=['SPX GEX', 'SPY GEX'], axis=0) # GEX coloration
            .format(format_dict, na_rep="")
        )
        st.dataframe(regime_styled, use_container_width=True, hide_index=True) # Reversed to show newest first

    tab_spy, tab_spx = st.tabs(["SPY Flow Ledger", "SPX Flow Ledger"])

    with tab_spy:
        spy_time = st.session_state.get('spy_update_time', 'Pending EOD Sync...')
        st.subheader(f"TOP 15 MOST TRADED STRIKES (Volume): SPY [Updated: {spy_time}]")
        st.dataframe(df_spy_vol.style.apply(style_sentiment, axis=1).format(format_dict, na_rep=""), use_container_width=True, hide_index=True)

        st.subheader(f"LARGEST INSTITUTIONAL SHIFTS (Δ OI): SPY [Updated: {spy_time}]")
        st.dataframe(df_spy_oi.style.apply(style_sentiment, axis=1).format(format_dict, na_rep=""), use_container_width=True, hide_index=True)

    with tab_spx:
        spx_time = st.session_state.get('spx_update_time', 'Pending EOD Sync...')
        st.subheader(f"TOP 15 MOST TRADED STRIKES (Volume): SPX [Updated: {spx_time}]")
        st.dataframe(df_spx_vol.style.apply(style_sentiment, axis=1).format(format_dict, na_rep=""), use_container_width=True, hide_index=True)

        st.subheader(f"LARGEST INSTITUTIONAL SHIFTS (Δ OI): SPX [Updated: {spx_time}]")
        st.dataframe(df_spx_oi.style.apply(style_sentiment, axis=1).format(format_dict, na_rep=""), use_container_width=True, hide_index=True)


# Custom styling for the GEX table columns
def style_gex_table(row):
    colors = ['font-size: 14px;'] * len(row)
    
    # Check if Friday for row shading
    if 'Date' in row.index:
        try:
            date_str = str(row['Date'])
            if datetime.datetime.strptime(date_str, '%Y-%m-%d').weekday() == 4:
                # Apply a subtle, very light blue tint
                colors = [c + ' background-color: rgba(65, 105, 225, 0.15);' for c in colors]
        except: pass
    
    # Total GEX Column Coloring
    if 'Total GEX' in row.index:
        try:
            val = float(str(row['Total GEX']).replace('$', '').replace('M', 'e6').replace('B', 'e9').replace('K', 'e3'))
            idx = row.index.get_loc('Total GEX')
            if val > 0: colors[idx] += ' color: #2ecc71; font-weight: bold;'
            elif val < 0: colors[idx] += ' color: #e74c3c; font-weight: bold;'
        except: pass
        
    # Spot GEX Column Coloring
    if 'Spot GEX' in row.index:
        try:
            val = float(str(row['Spot GEX']).replace('$', '').replace('M', 'e6').replace('B', 'e9').replace('K', 'e3'))
            idx = row.index.get_loc('Spot GEX')
            if val > 0: colors[idx] += ' color: #2ecc71; font-weight: bold;'
            elif val < 0: colors[idx] += ' color: #e74c3c; font-weight: bold;'
        except: pass
        
    # Vol POC (Magnet) Column Coloring
    if 'Vol POC' in row.index:
        val_str = str(row['Vol POC'])
        idx = row.index.get_loc('Vol POC')
        if '(C)' in val_str: colors[idx] += ' color: #2ecc71;'
        elif '(P)' in val_str: colors[idx] += ' color: #e74c3c;'
        
    # Accel (R) Column Coloring
    if 'Accel (R)' in row.index:
        idx = row.index.get_loc('Accel (R)')
        colors[idx] += ' color: #e74c3c; font-weight: bold;'
        
    # Flip Pt Column Coloring
    if 'Flip Pt' in row.index:
        idx = row.index.get_loc('Flip Pt')
        colors[idx] += ' color: #00bcd4; font-weight: bold;'
        
    return colors
# Custom styling for the Killbox table
def style_killbox_status(s):
    colors = []
    for val in s:
        val_str = str(val).upper()
        # Same scheme as terminal UI
        if "LIQUIDATION" in val_str: colors.append('background-color: #c0392b; color: white; font-weight: bold;')
        elif "BURNING" in val_str: colors.append('color: #e74c3c; font-weight: bold;')
        elif "TRAPPED BULLS" in val_str: colors.append('color: #2ecc71; font-weight: bold;') # Bull traps are good for bears
        elif "TRAPPED BEARS" in val_str: colors.append('color: #e74c3c; font-weight: bold;') # Bear traps are good for bulls
        elif "ROCKET FUEL" in val_str: colors.append('color: #e74c3c; font-weight: bold; background-color: rgba(231, 76, 60, 0.15);') 
        elif "RESISTANCE" in val_str: colors.append('color: #e74c3c; font-weight: bold; background-color: rgba(231, 76, 60, 0.15);')
        else: colors.append('color: #f39c12;')
    return colors

def style_killbox_delta_row(row):
    colors = [''] * len(row)
    try:
        if 'Net Δ' in row.index:
            idx = row.index.get_loc('Net Δ')
            status = str(row.get('Status', '')).upper()
            
            if "TRAPPED BEARS" in status or "RESISTANCE" in status or "ROCKET FUEL" in status:
                colors[idx] = 'color: #e74c3c; font-weight: bold;'
            elif "TRAPPED BULLS" in status:
                colors[idx] = 'color: #2ecc71; font-weight: bold;'
            else:
                clean_val = float(str(row['Net Δ']).replace('🐳', '').replace('$', '').replace('+', '').replace('M', 'e6').replace('K', 'e3'))
                if clean_val > 0: colors[idx] = 'color: #2ecc71; font-weight: bold;'
                else: colors[idx] = 'color: #e74c3c; font-weight: bold;'
    except: pass
    return colors

def style_killbox_fuse(s):
    colors = []
    for val in s:
        colors.append('')
    return colors
    
def style_killbox_row_background(row):
    styles = [''] * len(row)
    try:
        status = str(row.get('Status', '')).upper()
        if "TRAPPED BEARS" in status or "RESISTANCE" in status or "ROCKET FUEL" in status or "LIQUIDATION" in status or "BURNING" in status:
            bg = 'background-color: rgba(231, 76, 60, 0.08);'
        elif "TRAPPED BULLS" in status:
            bg = 'background-color: rgba(46, 204, 113, 0.08);'
        else:
            bg = ''
        styles = [bg] * len(row)
    except: pass
    return styles
    

with main_tab_killbox:
    hist_data = load_nexus_history()
    quant_data = load_nexus_quant()

    if not hist_data or not quant_data:
        st.warning("⚠️ Waiting for Backend Data..." )
    else:
        st.header("🎯 Killbox Analysis")
        ts = hist_data.get('trend_signals', {})
        
        # Structure Context
        st.markdown(f"**Trajectory:** {ts.get('trajectory', 'N/A')} &nbsp; | &nbsp; **Trend:** {ts.get('oi_trend', 'N/A')} &nbsp; | &nbsp; **Divergence Check:** {ts.get('divergence') or 'Clear'}")
        
        col_spx, col_spy = st.columns(2)
        
        def fmt_notional(val):
            if val == 0: return "$0"
            abs_val = abs(val)
            if abs_val >= 1e9:
                s = f"${abs_val/1e9:.1f}B"
            elif abs_val >= 1e6:
                s = f"${abs_val/1e6:.1f}M"
            else:
                s = f"${abs_val/1e3:.0f}K"
                
            if val >= 2_000_000: s = f"🐳 {s}"
            return f"+{s}" if val > 0 else f"-{s}"
            
        def process_kill_table(records, ticker):
            if not records: return pd.DataFrame()
            parsed = []
            for r in records:
                # Calculate fuse percentage
                strike = r.get('strike', 0)
                # Need rough spot to calculate fuse distance
                # Pull from major levels in quant data if existed, or approximate
                dist_str = f"{r.get('dist_pct', 0):.2f}%" if 'dist_pct' in r else "N/A"
                
                # We can calculate impact bar visually in pandas
                impact_raw = r.get('weighted_impact', 0)
                impact_str = "█" * max(1, min(10, int(impact_raw / 100))) # Approximation for Streamlit
                
                parsed.append({
                    "Strike": f"{strike:.1f}" if ticker == "SPX" else f"{strike:.0f}",
                    "DTE": f"{r.get('dte', 0):.0f}d",
                    "Dist %": dist_str,
                    "Net Δ": fmt_notional(r.get('notional_delta', 0)),
                    "Status": r.get('display_status', 'N/A'),
                    "Panic": f"{r.get('panic_score', 0):.1f}",
                    "_raw_delta": abs(float(r.get('notional_delta', 0))),
                    "_strike_val": float(strike)
                })
            df = pd.DataFrame(parsed)
            # Hierarchical grouping to cluster the highest absolute Delta weight at the top of each Strike
            df = df.sort_values(by=['_strike_val', '_raw_delta'], ascending=[False, False]).drop(columns=['_raw_delta', '_strike_val'])
            return df

        with col_spx:
            st.subheader("SPX Traps")
            df_spx_kb = process_kill_table(quant_data.get('spx_traps', []), 'SPX')
            if not df_spx_kb.empty:
                st.dataframe(
                    df_spx_kb.style
                    .apply(style_killbox_row_background, axis=1)
                    .apply(style_killbox_status, subset=['Status'])
                    .apply(style_killbox_delta_row, axis=1)
                    .apply(style_killbox_fuse, subset=['Dist %'])
                    .set_properties(**{'font-size': '15px'}), 
                    use_container_width=True, hide_index=True
                )
                
        with col_spy:
            st.subheader("SPY Traps")
            df_spy_kb = process_kill_table(quant_data.get('spy_traps', []), 'SPY')
            if not df_spy_kb.empty:
                st.dataframe(
                    df_spy_kb.style
                    .apply(style_killbox_row_background, axis=1)
                    .apply(style_killbox_status, subset=['Status'])
                    .apply(style_killbox_delta_row, axis=1)
                    .apply(style_killbox_fuse, subset=['Dist %'])
                    .set_properties(**{'font-size': '15px'}), 
                    use_container_width=True, hide_index=True
                )
        
        st.divider()

with main_tab_profiler:

    

    prof_data = load_nexus_profile()
    
    if not prof_data or 'gex_structure' not in prof_data:
        st.warning("⚠️ No SPX Profiler static table data found. Ensure `spx_profiler_nexus.py` is running and saving to Supabase.")
    else:
        spot_price = prof_data.get('spx_price', 0)
        gex_data = {
            'spot': spot_price,
            'gex_profiles': prof_data.get('gex_structure', []),
            'total_gamma': prof_data.get('net_gex', 0),
            'iv30': prof_data.get('gex_metrics', {}).get('iv30', 0)
        }

        def fmt_gex(val):
            if not val: return "$0K"
            val_abs = abs(val)
            s = f"${val_abs/1e9:.1f}B" if val_abs >= 1e9 else (f"${val_abs/1e6:.0f}M" if val_abs >= 1e6 else f"${val_abs/1e3:.0f}K")
            return "-" + s if val < 0 else s
            
        def fmt_s(val, basis=0):
            if not val or val == 0: return "N/A"
            if basis != 0:
                spy_est = (float(val) - basis) / 10
                return f"${float(val):.0f} ({spy_est:.1f})"
            return f"${float(val):.0f}"

        net_gex = gex_data.get('total_gamma', 0)
        net_gex_str = fmt_gex(net_gex)

        # We need the current basis spread to calculate SPY equivalents, we can extract it or default
        basis = 0
        iv = 0
        try:
            basis = prof_data.get('major_levels', {}).get('basis', 0) # Fallback if missing
            
            # Check levels file if available
            levels_path = '/Users/haydenscott/Desktop/Local Scripts/market_levels.json'
            import os
            if os.path.exists(levels_path):
                with open(levels_path, 'r') as lf:
                    level_data = json.load(lf)
                    basis = level_data.get('current_basis', 0)
                    iv = level_data.get('iv_30d', 0)
        except: pass

        # --- IV Range Calculation & Flow Extraction ---
        try:
            import math
            if iv == 0: iv = prof_data.get('gex_metrics', {}).get('iv30', 0)
            if iv == 0: iv = gex_data.get('iv30', 0) # Fallback to static if live is missing
            
            range_str = ""
            if spot_price > 0 and iv > 0:
                imp = spot_price * iv * math.sqrt(30.0/365.0)
                range_str = f" | <span style='color: #00bcd4; font-weight: bold;'>Range: {spot_price-imp:.0f}-{spot_price+imp:.0f} (IV:{iv:.1%})</span>"
        except:
            range_str = ""
            
        # Extract Flow Data directly from the main Profiler JSON dump
        fs = prof_data.get('flow_stats', {})
        net_flow = fs.get('cum_net_prem', 0)
        net_delta = fs.get('cum_net_delta', 0)
        
        # Generic d0+d1 fallback if both are exactly 0 and there's logic
        if net_flow == 0 and net_delta == 0:
            net_flow = fs.get('d0_net', 0) + fs.get('d1_net', 0)

        def safe_fmt(v, plus=False):
            if not v: return "$0K"
            val_abs = abs(v)
            s = f"${val_abs/1e9:.2f}B" if val_abs>=1e9 else (f"${val_abs/1e6:.1f}M" if val_abs>=1e6 else f"${val_abs/1e3:.0f}K")
            if v > 0 and plus: return "+" + s
            if v < 0: return "-" + s
            return s

        net_flow_str = f"<span style='color: {'#2ecc71' if net_flow > 0 else '#e74c3c'}; font-weight: bold;'>{safe_fmt(net_flow, True)}</span>"
        net_delta_str = f"<span style='color: {'#2ecc71' if net_delta > 0 else '#e74c3c'}; font-weight: bold;'>{safe_fmt(net_delta, True)}</span>"
        
        st.markdown(
            f"""
            <div style="background-color: #000; color: #fff; padding: 15px; border-radius: 5px; font-family: monospace; font-size: 14px; position: relative;">
                <div style="position: absolute; right: 15px; top: 15px; color: #a0a0a0;">Next Scan: <span style="color: #00bcd4; font-weight: bold;">{60 - (int(datetime.datetime.now().timestamp()) % 60)}s</span></div>
                <b>SPX: <span style="font-size: 16px;">${spot_price:,.2f}</span></b> 
                (SPY ~${(spot_price - basis)/10:.2f}) [Spread: {basis:+.2f}] 
                | <span style="color: #fff;">Net Flow:</span> {net_flow_str} 
                | <span style="color: #fff;">Net Delta:</span> {net_delta_str}
                | <span style="color: #e91e63;">Magnet: ${prof_data.get('major_levels', {}).get('magnet', 0):.0f}</span> {range_str}
            </div>
            """, unsafe_allow_html=True
        )
        st.divider()
        
        profiles = gex_data['gex_profiles']
        table_rows = []
        
        for idx, p in enumerate(profiles):
            # Attempt to extract Date if standard format exists, otherwise try to extract it from the raw chain dates if we injected them
            date_str = p.get('date', '')
            try:
                date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                dte = (date_obj - datetime.datetime.now().date()).days
            except:
                dte = "?"
                # Fallback to calculating from index if dates array is in parent
                try:
                    if 'dates' in gex_data:
                        date_str = str(gex_data['dates'][idx])
                        date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                        dte = (date_obj - datetime.datetime.now().date()).days
                except: pass
                
            if isinstance(dte, int) and dte > 14:
                continue
                
            poc_str = "N/A"
            if p.get('volume_poc_strike'):
                sent = "C" if p.get('volume_poc_call_vol', 0) > p.get('volume_poc_put_vol', 0) else "P"
                poc_str = f"{fmt_s(p['volume_poc_strike'], basis)} ({sent})"
                
            table_rows.append({
                "Date": date_str,
                "DTE": str(dte),
                "Total GEX": fmt_gex(p.get('total_gamma')),
                "Spot GEX": fmt_gex(p.get('spot_gamma')),
                "Max Pain": fmt_s(p.get('max_pain_strike'), basis),
                "Vol POC": poc_str,
                "Flip Pt": fmt_s(p.get('gex_flip_point'), basis),
                "Accel (R)": fmt_s(p.get('short_gamma_wall_above'), basis),
                "Pin (S)": fmt_s(p.get('short_gamma_wall_below'), basis),
                "P/C (Vol)": f"{p.get('pc_ratio_volume') or 0:.2f}",
                "P/C (OI)": f"{p.get('pc_ratio_oi') or 0:.2f}"
            })
            
        df_profiler = pd.DataFrame(table_rows)
        
        styled_df = (
            df_profiler.style
            .apply(style_gex_table, axis=1)
        )
        
        st.dataframe(styled_df, use_container_width=True, hide_index=True)


with main_tab_profiler_spy:
    
    prof_data = load_nexus_spy_profile()
    
    if not prof_data or 'gex_structure' not in prof_data:
        st.warning("⚠️ No SPY Profiler static table data found. Ensure `viewer_dash_nexus.py` is running and saving to Supabase.")
    else:
        spot_price = prof_data.get('current_price', 0)
        net_gex = prof_data.get('net_gex', 0)
        
        raw_mag = prof_data.get('magnet', 0)
        if isinstance(raw_mag, dict): magnet = raw_mag.get('strike', 0)
        else: magnet = float(raw_mag) if raw_mag else 0
            
        raw_zero = prof_data.get('zero_gamma', 0)
        if isinstance(raw_zero, dict): zero_gamma = raw_zero.get('strike', 0)
        else: zero_gamma = float(raw_zero) if raw_zero else 0
        
        def fmt_gex(val):
            if not val: return "$0K"
            val_abs = abs(val)
            if val_abs >= 1e9: return f"{'$-' if val < 0 else '$'}{val_abs/1e9:.1f}B"
            if val_abs >= 1e6: return f"{'$-' if val < 0 else '$'}{val_abs/1e6:.0f}M"
            return f"{'$-' if val < 0 else '$'}{val_abs/1e3:.0f}K"
            
        def fmt_s(val):
            if not val or val == 0: return "N/A"
            if isinstance(val, dict):
                val = val.get('strike', 0)
            if float(val) == 0: return "N/A"
            return f"${float(val):.0f}"

        # New Metrics
        net_flow = prof_data.get('net_premium', 0)
        net_delta = prof_data.get('net_delta', 0)
        futures_implied = prof_data.get('futures_implied', 0)
        
        def safe_fmt(v, plus=False):
            if not v: return "$0K"
            val_abs = abs(v)
            s = f"${val_abs/1e9:.2f}B" if val_abs>=1e9 else (f"${val_abs/1e6:.1f}M" if val_abs>=1e6 else f"${val_abs/1e3:.0f}K")
            if v > 0 and plus: return "+" + s
            if v < 0: return "-" + s
            return s
            
        net_flow_str = f"<span style='color: {'#2ecc71' if net_flow > 0 else '#e74c3c'}; font-weight: bold;'>{safe_fmt(net_flow, True)}</span>"
        net_delta_str = f"<span style='color: {'#2ecc71' if net_delta > 0 else '#e74c3c'}; font-weight: bold;'>{safe_fmt(net_delta, True)}</span>"
        
        implied_str = ""
        if futures_implied > 0 and spot_price > 0:
            imp_diff = futures_implied - spot_price
            implied_str = f"<br><span style='color: #888;'>Futures Implied: ${futures_implied:.2f} (<span style='color: {'#2ecc71' if imp_diff >= 0 else '#e74c3c'};'>{imp_diff:+.2f}</span>)</span>"

        # --- IV Range Calculation ---
        try:
            import math, os, json
            iv = 0
            
            levels_path = '/Users/haydenscott/Desktop/Local Scripts/market_levels.json'
            if os.path.exists(levels_path):
                with open(levels_path, 'r') as lf:
                    level_data = json.load(lf)
                    iv = level_data.get('iv_30d', 0)
                    
            if iv == 0: iv = prof_data.get('gex_metrics', {}).get('iv30', 0)
            
            range_str = ""
            if spot_price > 0 and iv > 0:
                imp = spot_price * iv * math.sqrt(30.0/365.0)
                range_str = f" | <span style='color: #00bcd4; font-weight: bold;'>Range: {spot_price-imp:.0f}-{spot_price+imp:.0f} (IV:{iv:.1%})</span>"
        except:
            range_str = ""

        st.markdown(
            f'''
            <div style="background-color: #000; color: #fff; padding: 15px; border-radius: 5px; font-family: monospace; font-size: 14px; position: relative;">
                <div style="position: absolute; right: 15px; top: 15px; color: #a0a0a0;">Next Scan: <span style="color: #00bcd4; font-weight: bold;">{60 - (int(datetime.datetime.now().timestamp()) % 60)}s</span></div>
                <b>SPY: <span style="font-size: 16px;">${spot_price:,.2f}</span></b> 
                | <span style="color: #fff;">Net Prem:</span> {net_flow_str}
                | <span style="color: #fff;">Net Delta:</span> {net_delta_str}
                | <span style="color: #e91e63;">Magnet: ${magnet:.0f}</span>{range_str}{implied_str}
            </div>
            ''', unsafe_allow_html=True
        )
        st.divider()
        
        profiles = prof_data['gex_structure']
        table_rows = []
        
        for idx, p in enumerate(profiles):
            date_str = p.get('date', '')
            try:
                date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                dte = (date_obj - datetime.datetime.now().date()).days
            except:
                dte = "?"
                
            if isinstance(dte, int) and dte > 14:
                continue
                
            poc_str = "N/A"
            if p.get('volume_poc_strike'):
                sent = "C" if p.get('volume_poc_call_vol', 0) > p.get('volume_poc_put_vol', 0) else "P"
                poc_str = f"{fmt_s(p['volume_poc_strike'])} ({sent})"
                
            table_rows.append({
                "Date": date_str,
                "DTE": str(dte),
                "Total GEX": fmt_gex(p.get('total_gamma')),
                "Spot GEX": fmt_gex(p.get('spot_gamma')),
                "Max Pain": fmt_s(p.get('max_pain_strike')),
                "Vol POC": poc_str,
                "Flip Pt": fmt_s(p.get('gex_flip_point')),
                "Accel (R)": fmt_s(p.get('short_gamma_wall_above', p.get('long_gamma_wall_above'))),
                "Pin (S)": fmt_s(p.get('short_gamma_wall_below')),
                "P/C (Vol)": f"{p.get('pc_ratio_volume') or 0:.2f}",
                "P/C (OI)": f"{p.get('pc_ratio_oi') or 0:.2f}"
            })
            
        if table_rows:
            df_profiler = pd.DataFrame(table_rows)
            styled_df = (
                df_profiler.style
                .apply(style_gex_table, axis=1)
            )
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
        else:
            st.info("No timeline data generated yet.")

with main_tab_oi_book:
    oi_data = load_oi_book()
    
    if not oi_data:
        st.warning("⚠️ No OI Book data found. Ensure `nexus_oi_book.py` is running and pushing payloads up securely to Supabase.")
    else:
        spot = oi_data.get("spot", 0)
        iv30 = oi_data.get("iv30", 0)
        imp_move = oi_data.get("implied_move", 0)
        updated_ts = oi_data.get("updated_at", 0)
        up_str = datetime.datetime.fromtimestamp(updated_ts).strftime('%H:%M:%S ET') if updated_ts else "Unknown"
        
        st.markdown(
            f'''
            <div style="background-color: #000; color: #fff; padding: 15px; border-radius: 5px; font-family: monospace; font-size: 14px; position: relative;">
                <div style="position: absolute; right: 15px; top: 15px; color: #a0a0a0;">Last Scan: <span style="color: #00bcd4; font-weight: bold;">{up_str}</span></div>
                <b>Deep OI Scan</b> 
                | <span style="color: #fff;">Spot:</span> ${spot:.2f}
                | <span style="color: #fff;">IV30:</span> {iv30:.1%}
                | <span style="color: #e91e63;">Implied Move: +/-${imp_move:.2f}</span>
            </div>
            ''', unsafe_allow_html=True
        )
        st.divider()
        
        agg = oi_data.get("agg", {})
        
        # Build DataFrame
        rows = []
        for stk_str, data in agg.items():
            stk = float(stk_str)
            p_oi = data.get('P', {}).get('oi', 0)
            p_vol = data.get('P', {}).get('vol', 0)
            c_oi = data.get('C', {}).get('oi', 0)
            c_vol = data.get('C', {}).get('vol', 0)
            
            rows.append({
                "Put OI": p_oi,
                "Put Vol": p_vol,
                "Strike": stk,
                "Call Vol": c_vol,
                "Call OI": c_oi
            })
            
        if rows:
            df_oi = pd.DataFrame(rows).sort_values("Strike")
            
            def fmt(val):
                if val >= 1000: return f"{val/1000:.1f}k"
                elif val == 0: return ""
                return str(int(val))
                
            put_labels = [f"{fmt(oi)} [V:{fmt(vol)}]" if oi > 0 or vol > 0 else "" for oi, vol in zip(df_oi["Put OI"], df_oi["Put Vol"])]
            call_labels = [f"[V:{fmt(vol)}] {fmt(oi)}" if oi > 0 or vol > 0 else "" for vol, oi in zip(df_oi["Call Vol"], df_oi["Call OI"])]
            
            # Melt for Altair (Negative Put Values to branch left)
            df_melt = pd.DataFrame({
                "Strike": df_oi["Strike"].tolist() * 2,
                "Open Interest": [-x for x in df_oi["Put OI"]] + df_oi["Call OI"].tolist(),
                "Volume": df_oi["Put Vol"].tolist() + df_oi["Call Vol"].tolist(),
                "Type": ["Put"] * len(df_oi) + ["Call"] * len(df_oi),
                "Label": put_labels + call_labels
            })
            
            max_oi = max(df_oi["Put OI"].max(), df_oi["Call OI"].max())
            max_oi = max_oi * 1.25 # Add 25% padding to domain to fit the text labels comfortably
            
            # We want to format the tooltip to show absolute values for Puts instead of negative
            base = alt.Chart(df_melt).encode(
                y=alt.Y("Strike:O", sort="descending", title="Strike Price", axis=alt.Axis(grid=True)),
                x=alt.X("Open Interest:Q", title="Open Interest", scale=alt.Scale(domain=[-max_oi, max_oi])),
                color=alt.Color("Type:N", scale=alt.Scale(domain=["Call", "Put"], range=["#2e7d32", "#d32f2f"]), legend=alt.Legend(title="Option Type")),
                tooltip=[
                    alt.Tooltip("Strike", title="Strike"), 
                    alt.Tooltip("Type", title="Type"), 
                    alt.Tooltip("Volume:Q", title="Volume"),
                    # Altair expr to calculate absolute value of OI for tooltip
                    alt.Tooltip("abs(datum['Open Interest']):Q", title="Open Interest")
                ]
            )
            
            # Create explicit text layers dynamically mirroring axis
            put_text = base.mark_text(
                align='right',
                baseline='middle',
                dx=-5,
                fontSize=12,
                fontWeight=500
            ).transform_filter(
                alt.datum.Type == 'Put'
            ).encode(
                text='Label:N'
            )
            
            call_text = base.mark_text(
                align='left',
                baseline='middle',
                dx=5,
                fontSize=12,
                fontWeight=500
            ).transform_filter(
                alt.datum.Type == 'Call'
            ).encode(
                text='Label:N'
            )
            
            # Dynamically scale height based on the number of visible strikes
            num_strikes = len(df_oi["Strike"].unique())
            chart_height = max(800, num_strikes * 22)
            
            base = base.properties(
                title="Options Open Interest Distribution (Butterfly)",
                height=chart_height
            )
            
            # Reference Line at Spot
            spot_line = alt.Chart(pd.DataFrame({'Spot': [spot]})).mark_rule(color='#e91e63', strokeWidth=2).encode(
                y='Spot:O'
            )
            
            # Layer the components: Bars + Text + Spot Line
            st.altair_chart((base.mark_bar() + put_text + call_text + spot_line).interactive(), use_container_width=True)
            
            st.divider()
            
            _, col_center, _ = st.columns([0.15, 0.7, 0.15])
            with col_center:
                st.subheader("Raw Matrix Data")
                df_display = df_oi.sort_values("Strike", ascending=False).copy()
                
                # Apply styling for comma formats and to center the strike column visually
                styled_df = df_display.style.format({
                    "Put OI": "{:,.0f}",
                    "Put Vol": "{:,.0f}",
                    "Strike": "${:,.0f}",
                    "Call Vol": "{:,.0f}",
                    "Call OI": "{:,.0f}"
                }).set_properties(subset=['Strike'], **{'font-weight': 'bold', 'text-align': 'center', 'background-color': 'rgba(128, 128, 128, 0.1)'})
                
                st.dataframe(styled_df, use_container_width=True, hide_index=True)

with main_tab_mtf:
    st.header("⏱️ MTF Nexus Analysis")
    st.caption("Statistical boundaries based on Multiple Time Frame momentum and Volatility Standard Deviation.")
    
    mtf_data = load_mtf_nexus()
    if not mtf_data:
        st.warning("MTF Nexus Telemetry is currently offline. Ensure `mtf_nexus.py` is actively syncing to Supabase.")
    else:
        # Create columns dynamically based on tickers (Usually 2: SPY and $SPX.X)
        cols = st.columns(max(1, len(mtf_data)))
        for col, (ticker, data) in zip(cols, mtf_data.items()):
            with col:
                st.subheader(f"Tracker: {ticker}")
                
                # Metric Cards
                metrics_col1, metrics_col2 = st.columns(2)
                metrics_col1.metric("Current Price", data.get("price_str", "-"))
                
                slope = data.get("slope", 0.0)
                slope_color = "normal" if slope >= -5 else "inverse"
                metrics_col2.metric("Daily Trend Slope", f"{slope}°", delta=str(slope) if slope != 0 else None, delta_color=slope_color)
                
                # Status Alert box
                status = data.get("status", "NEUTRAL")
                if "BULLISH" in status:
                    st.success(f"**Algo State:** {status}")
                elif "BEARISH" in status:
                    st.error(f"**Algo State:** {status}")
                else:
                    st.info(f"**Algo State:** {status}")
                
                st.divider()
                st.markdown("#### McMillan Volatility Matrix")
                
                mc_display = data.get("mc_display", "WAIT")
                mc_target = data.get("mc_target", "-")
                
                try: # Strip exact bracket color strings from Textual for clean Streamlit printing
                    import re
                    mc_clean = re.sub(r'\[.*?\]', '', mc_display)
                except Exception:
                    mc_clean = mc_display
                
                st.write(f"**Band Status:** `{mc_clean}`")
                st.write(f"**Reversion Range:** {mc_target}")
                st.write(f"**SMA 20 Baseline:** ${data.get('daily_sma', '-')}")
                
                st.divider()
                st.markdown("#### Quantitative Positioning")
                spreads = data.get("spreads", "-")
                for spread in spreads.split(' | '):
                    st.code(spread, language="markdown")
                
                st.caption(f"Last updated: {data.get('timestamp', 'Unknown').replace('T', ' ')[:19]}")
