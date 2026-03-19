import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import asyncio
from supabase_bridge import upload_json_to_supabase

CREDENTIALS_FILE = "tribal-flux-476216-c0-70e4f946eb77.json"
SHEET_ID = '1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg'

def update_google_sheet_ledger():
    print("Authenticate and load data from Google Sheets...")
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        wb = client.open_by_key(SHEET_ID)
        ws = wb.worksheet("Historical Data")
        data = ws.get_all_values()
        
        if not data or len(data) < 2:
            print("❌ ABORT: Historical Data tab is empty or only has headers.")
            return
            
        headers = data[0]
        df = pd.DataFrame(data[1:], columns=headers)
        print(f"Loaded {len(df)} rows.")
    except Exception as e:
        print(f"Error loading data: {e}")
        return

    # Process exactly like terminal script
    date_col = 'Trade Date'
    strike_col = 'Strike'
    type_col = 'Type'
    oi_col = 'Open Interest'
    vol_col = 'Volume'
    exp_col = 'Expiration' # Added Expiration column

    df[date_col] = pd.to_datetime(df[date_col], format='mixed', errors='coerce')
    df[strike_col] = pd.to_numeric(df[strike_col], errors='coerce')
    df[oi_col] = pd.to_numeric(df[oi_col], errors='coerce').fillna(0)
    df[vol_col] = pd.to_numeric(df[vol_col], errors='coerce').fillna(0)
    df = df.dropna(subset=[date_col, strike_col])
    
    # [FIX] Filter out SPX options to strictly isolate SPY options (strikes < 3000)
    # We only want to analyze SPY index options per the user's request.
    df = df[df[strike_col] < 3000].copy()

    # Load the TRADESTATION EOD Spot Price generated continuously by TS_Nexus
    ts_spot = 0.0
    import os
    import json
    if os.path.exists("market_state.json"):
        try:
            with open("market_state.json", "r") as f:
                m_state = json.load(f)
                ts_spot = float(m_state.get("market_structure", {}).get("SPY", {}).get("price", 0))
        except Exception as e: print(f"⚠️ Could not load TS_Nexus SPY spot price: {e}")

    # [FIX] Filter out Deep ITM/OTM noise. Only keep strikes within 12% of the current spot price.
    # This filters out the 4000s and 5000s that are stock replacement hedges and useless for 7DTE credit spreads.
    if ts_spot > 0:
        df = df[abs(df[strike_col] - ts_spot) / ts_spot <= 0.12].copy()

    unique_dates = sorted(df[date_col].dt.date.unique())
    if len(unique_dates) == 0:
        print("❌ ABORT: No valid unique Trade Dates found after parsing.")
        # Debugging Print to see what Pandas sees:
        print(f"Sample Dates: {df[date_col].head()}")
        return
        
    last_5_days = unique_dates[-5:]
    print(f"Filtering dataset down to last 5 days: {last_5_days}")
    df_filtered = df[df[date_col].dt.date.isin(last_5_days)].copy()

    # [FIX] Filter out < 1 DTE from the aggregate to isolate forward-looking flow
    df_filtered[exp_col] = pd.to_datetime(df_filtered[exp_col], format='mixed', errors='coerce')
    latest_trade_date = last_5_days[-1]
    df_filtered = df_filtered[df_filtered[exp_col].dt.date > latest_trade_date]

    # Aggregate by Trade Date, Strike, Type AND Expiration to keep granularity
    daily_aggregated = df_filtered.groupby([date_col, strike_col, type_col, exp_col], as_index=False).agg({vol_col: 'sum', oi_col: 'sum'})

    results = []
    # Group by Strike and Type to find the top shifts
    for (strike, opt_type), group in daily_aggregated.groupby([strike_col, type_col]):
        
        # We need to find the overall Net Change and Volume across the whole strike first
        # So we aggregate the granual expiration data back into trade dates
        strike_daily = group.groupby(date_col).agg({vol_col: 'sum', oi_col: 'sum'}).reset_index().sort_values(by=date_col)
        
        if strike_daily.empty: continue
            
        total_volume = strike_daily[vol_col].sum()
        first_oi = strike_daily.iloc[0][oi_col]
        last_oi = strike_daily.iloc[-1][oi_col]
        net_oi_change = last_oi - first_oi
        
        # New Indicator: Vol/OI
        raw_vol_oi = float(total_volume / first_oi) if first_oi > 0 else 0.0
        vol_oi_ratio = f"{raw_vol_oi:.2f}"
        
        # New Indicator: RVOL (assuming last day is "Today")
        today_vol = strike_daily.iloc[-1][vol_col]
        # RVOL = Today_Vol / (Total_Vol / Days), guarded against zero
        num_days = len(strike_daily)
        avg_vol = total_volume / num_days if num_days > 0 else 0
        raw_rvol = float(today_vol / avg_vol) if avg_vol > 0 else 0.0
        rvol = f"{raw_rvol:.2f}"
        
        # New Indicator: Δ² OI (OI Acceleration: Today's Net Change - Yesterday's Net Change)
        delta_sq_oi = 0
        if num_days >= 2:
            today_oi_change = strike_daily.iloc[-1][oi_col] - strike_daily.iloc[-2][oi_col]
            yesterday_oi_change = strike_daily.iloc[-2][oi_col] - (strike_daily.iloc[-3][oi_col] if num_days >= 3 else strike_daily.iloc[-2][oi_col])
            delta_sq_oi = today_oi_change - yesterday_oi_change

        # Now, find the single Expiration date within this Strike that had the highest volume over these 5 days
        exp_volumes = group.groupby(exp_col)[vol_col].sum()
        top_exp = exp_volumes.idxmax() if not exp_volumes.empty else "N/A"
        if hasattr(top_exp, 'strftime'):
            top_exp = top_exp.strftime('%Y-%m-%d')
        
        results.append({
            'Strike': strike, 'Type': opt_type, 'Top Expiration': top_exp, 'Total Volume': total_volume,
            'Start OI': first_oi, 'End OI': last_oi, 'Δ OI': net_oi_change,
            'Vol/OI': vol_oi_ratio, 'RVOL': rvol, 'Δ² OI': delta_sq_oi
        })

    results_df = pd.DataFrame(results)

    top_vol = results_df.sort_values(by='Total Volume', ascending=False).head(15)
    results_df['Abs_OI'] = results_df['Δ OI'].abs()
    top_oi = results_df.sort_values(by='Abs_OI', ascending=False).drop(columns=['Abs_OI']).head(15)

    try:
        try:
            out_ws = wb.worksheet("SPY 5-Day Flow Ledger")
        except:
            out_ws = wb.add_worksheet(title="SPY 5-Day Flow Ledger", rows=100, cols=10)
        
        print("Clearing Output Ledger tab...")
        out_ws.clear()
        
        s_date = last_5_days[0].strftime('%Y-%m-%d')
        e_date = last_5_days[-1].strftime('%Y-%m-%d')
        
        # ts_spot is now fetched globally at the top of the file
        
        updates = []
        updates.append([f"TOP 15 MOST TRADED STRIKES ({s_date} to {e_date})", "", "", "", "", "", "", "TS_Nexus SPY Spot $\\rightarrow$", f"${ts_spot:.2f}"])
        
        # Build headers with the new static string columns
        base_columns = list(top_vol.columns)
        full_headers = base_columns + ["Dist %", "Sentiment"]
        updates.append(full_headers)
        
        def calculate_sentiment_and_dist(strike, opt_type, doi, spot):
            dist_str = ""
            sentiment_str = "Other"
            if spot > 0:
                dist = abs(strike - spot) / spot
                dist_str = f"{dist * 100:.1f}%"
                if doi > 0: # Option Open Interest Built Up (Added)
                    if opt_type == "Put":
                        sentiment_str = "Bullish (Short Put Buildup)" if strike < spot else "Bearish (Long Put Buildup)"
                    elif opt_type == "Call":
                        sentiment_str = "Bearish (Short Call Buildup)" if strike > spot else "Bullish (Long Call Buildup)"
                elif doi < 0: # Option Open Interest Dropped (Covered/Closed)
                    if opt_type == "Put":
                        sentiment_str = "Bearish (Short Put Cover)" if strike < spot else "Bullish (Long Put Close)"
                    elif opt_type == "Call":
                        sentiment_str = "Bullish (Short Call Cover)" if strike > spot else "Bearish (Long Call Close)"
            return dist_str, sentiment_str

        # Inject static string calculations into Top Vol
        top_vol['Dist %'] = ""
        top_vol['Sentiment'] = "Other"
        
        for i, row in enumerate(top_vol.itertuples(index=False)):
            row_list = list(row)
            
            strike = float(str(row_list[0]).replace(',', ''))
            opt_type = row_list[1]
            doi = float(str(row_list[6]).replace(',', ''))
            
            dist_str, sent_str = calculate_sentiment_and_dist(strike, opt_type, doi, ts_spot)
            
            # Apply to DataFrame inline
            top_vol.loc[top_vol.index[i], 'Dist %'] = dist_str
            top_vol.loc[top_vol.index[i], 'Sentiment'] = sent_str
            
            row_list.extend([dist_str, sent_str])
            updates.append(row_list)
        
        updates.append(["", "", "", "", "", "", "", "", ""])
        updates.append([f"LARGEST INSTITUTIONAL SHIFTS (Top 15 Net Change in OI)", "", "", "", "", "", "", "", ""])
        updates.append(full_headers)
        
        # Inject static string calculations into Top OI
        top_oi['Dist %'] = ""
        top_oi['Sentiment'] = "Other"
        
        for i, row in enumerate(top_oi.itertuples(index=False)):
            row_list = list(row)
            
            strike = float(str(row_list[0]).replace(',', ''))
            opt_type = row_list[1]
            doi = float(str(row_list[6]).replace(',', ''))
            
            dist_str, sent_str = calculate_sentiment_and_dist(strike, opt_type, doi, ts_spot)
            
            # Apply to DataFrame inline
            top_oi.loc[top_oi.index[i], 'Dist %'] = dist_str
            top_oi.loc[top_oi.index[i], 'Sentiment'] = sent_str
            
            row_list.extend([dist_str, sent_str])
            updates.append(row_list)

        print("Writing to sheet...")
        # Since we removed GOOGLEFINANCE formulas, we don't need USER_ENTERED anymore. Use standard format.
        out_ws.append_rows(updates)
        
        print("Applying Conditional Formatting Rules...")
        sheet_id = out_ws.id
        
        print("Applying Conditional Formatting Rules (White Text & Colors)...")
        sheet_id = out_ws.id
        
        # We rely on the delete block below to wipe rules, no need to inject an empty one here.
        # Ensure we don't stack thousands of rules over time
        
        # Ranges for Type (1) and Sentiment (11)
        target_ranges = [
            {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 50, "startColumnIndex": 1, "endColumnIndex": 2},
            {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 50, "startColumnIndex": 11, "endColumnIndex": 12}
        ]
        
        # Rule 1: GREEN Text for ANY Bullish Sentiment
        # Condition: Column L text contains "Bullish"
        rule_green = {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": target_ranges,
                    "booleanRule": {
                        "condition": {
                            "type": "TEXT_CONTAINS",
                            "values": [{"userEnteredValue": 'Bullish'}]
                        },
                        "format": {
                            "textFormat": {"foregroundColor": {"red": 0.15, "green": 0.50, "blue": 0.15}, "bold": True} # Dark Green Text
                        }
                    }
                },
                "index": 0
            }
        }
        
        # Rule 2: RED Text for ANY Bearish Sentiment
        # Condition: Column L text contains "Bearish"
        rule_red = {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": target_ranges,
                    "booleanRule": {
                        "condition": {
                            "type": "TEXT_CONTAINS",
                            "values": [{"userEnteredValue": '*Bearish*'}]
                        },
                        "format": {
                            "textFormat": {"foregroundColor": {"red": 0.70, "green": 0.10, "blue": 0.10}, "bold": True} # Dark Red Text
                        }
                    }
                },
                "index": 1
            }
        }
        
        # Clear existing rules first (Robust individual deletion until empty)
        print("Clearing old conditional formatting rules...")
        deleted_count = 0
        while True:
            try:
                clear_req = {"deleteConditionalFormatRule": {"index": 0, "sheetId": sheet_id}}
                wb.batch_update({"requests": [clear_req]})
                deleted_count += 1
            except Exception:
                # API throws an error when no rules are left to delete at index 0
                break
        print(f"Deleted {deleted_count} old rules.")
        
        # Push new rules
        wb.batch_update({"requests": [rule_green, rule_red]})
        
        print("Successfully published to SPY 5-Day Flow Ledger tab!")
        
        # [NEW] DUAL-WRITE TO SUPABASE
        print("☁️ Syncing SPY 5-Day Flow Ledger to Supabase...")
        
        # Convert the DataFrame to JSON-serializable records
        # Keep empty strings and formatted numbers exactly as they are sent to Sheets
        import datetime
        import pytz
        est = pytz.timezone('US/Eastern')
        payload = {
            "top_vol": top_vol.fillna("").to_dict(orient='records'),
            "top_oi": top_oi.fillna("").to_dict(orient='records'),
            "spot_price": f"${ts_spot:.2f}",
            "last_updated": datetime.datetime.now(est).strftime("%m/%d/%y %H:%M ET")
        }
        
        # We use asyncio.run because this sync script doesn't have an event loop yet
        asyncio.run(upload_json_to_supabase("nexus_profile", payload, id_field="id", id_value="spy_flow_ledger"))
        print("✅ SYNCHRONIZED SPY LEDGER WITH SUPABASE")
        
    except Exception as e:
        print(f"Error writing to sheet: {e}")

if __name__ == "__main__":
    update_google_sheet_ledger()
