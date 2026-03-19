import re

with open("app.py", "r") as f:
    content = f.read()

# 1. Update tabs
content = content.replace(
    'main_tab_mr, main_tab_profiler = st.tabs(["Market Regime & Options Flow", "SPX Profiler"])',
    'main_tab_mr, main_tab_profiler, main_tab_profiler_spy = st.tabs(["Market Regime & Options Flow", "SPX Profiler", "SPY Profiler"])'
)

# 2. Add load_nexus_spy_profile
load_spy_func = """
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
"""

content = content.replace(
    "@st.cache_data(ttl=30)\ndef load_nexus_profile():",
    load_spy_func + "\n@st.cache_data(ttl=30)\ndef load_nexus_profile():"
)

# 3. Add SPY Tab rendering logic
spy_tab_content = """
with main_tab_profiler_spy:
    st_autorefresh(interval=1000, key="profiler_tick_spy")
    
    prof_data = load_nexus_spy_profile()
    
    if not prof_data or 'gex_structure' not in prof_data:
        st.warning("⚠️ No SPY Profiler static table data found. Ensure `viewer_dash_nexus.py` is running and saving to Supabase.")
    else:
        spot_price = prof_data.get('current_price', 0)
        net_gex = prof_data.get('net_gex', 0)
        magnet = prof_data.get('magnet', 0)
        zero_gamma = prof_data.get('zero_gamma', 0)
        
        def fmt_gex(val):
            if not val: return "$0K"
            val_abs = abs(val)
            if val_abs >= 1e9: return f"{'$-' if val < 0 else '$'}{val_abs/1e9:.1f}B"
            if val_abs >= 1e6: return f"{'$-' if val < 0 else '$'}{val_abs/1e6:.0f}M"
            return f"{'$-' if val < 0 else '$'}{val_abs/1e3:.0f}K"
            
        def fmt_s(val):
            if not val or val == 0: return "N/A"
            return f"${float(val):.0f}"

        net_gex_str = fmt_gex(net_gex)

        st.markdown(
            f'''
            <div style="background-color: #000; color: #fff; padding: 15px; border-radius: 5px; font-family: monospace; font-size: 14px; position: relative;">
                <div style="position: absolute; right: 15px; top: 15px; color: #a0a0a0;">Next Scan: <span style="color: #00bcd4; font-weight: bold;">{60 - (int(datetime.datetime.now().timestamp()) % 60)}s</span></div>
                <b>SPY: <span style="font-size: 16px;">${spot_price:,.2f}</span></b> 
                | <span style="color: #fff;">Net Gamma:</span> <span style="color: {'#2ecc71' if net_gex > 0 else '#e74c3c'}; font-weight: bold;">{net_gex_str}</span>
                | <span style="color: #e91e63;">Magnet: ${magnet:.0f}</span>
                | <span style="color: #00bcd4;">Zero Gamma: ${zero_gamma:.0f}</span>
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
"""

with open("app.py", "w") as f:
    f.write(content + "\n" + spy_tab_content)

print("Patched app.py!")
