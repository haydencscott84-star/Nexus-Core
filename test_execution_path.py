import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

CREDENTIALS_FILE = "tribal-flux-476216-c0-70e4f946eb77.json"
SHEET_ID = '1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg'

p1 = False
p2 = False
p3 = False

try:
    print("Authenticate and load data from Google Sheets...")
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    wb = client.open_by_key(SHEET_ID)
    ws = wb.worksheet("Historical Data")
    data = ws.get_all_values()
    
    headers = data[0]
    df = pd.DataFrame(data[1:], columns=headers)
    
    date_col = 'Trade Date'
    strike_col = 'Strike'
    type_col = 'Type'
    oi_col = 'Open Interest'
    vol_col = 'Volume'
    exp_col = 'Expiration'

    df[date_col] = pd.to_datetime(df[date_col], format='mixed', errors='coerce')
    df[strike_col] = pd.to_numeric(df[strike_col], errors='coerce')
    df[oi_col] = pd.to_numeric(df[oi_col], errors='coerce').fillna(0)
    df[vol_col] = pd.to_numeric(df[vol_col], errors='coerce').fillna(0)
    df = df.dropna(subset=[date_col, strike_col])

    unique_dates = sorted(df[date_col].dt.date.unique())
    last_5_days = unique_dates[-5:]
    df_filtered = df[df[date_col].dt.date.isin(last_5_days)].copy()

    daily_aggregated = df_filtered.groupby([date_col, strike_col, type_col, exp_col], as_index=False).agg({vol_col: 'sum', oi_col: 'sum'})
    p1 = True

    results = []
    print("Entering Grouping Loop...")
    for (strike, opt_type), group in daily_aggregated.groupby([strike_col, type_col]):
        strike_daily = group.groupby(date_col).agg({vol_col: 'sum', oi_col: 'sum'}).reset_index().sort_values(by=date_col)
        
        if strike_daily.empty: continue
            
        total_volume = strike_daily[vol_col].sum()
        first_oi = strike_daily.iloc[0][oi_col]
        last_oi = strike_daily.iloc[-1][oi_col]
        net_oi_change = last_oi - first_oi
        
        vol_oi_ratio = round(total_volume / first_oi, 2) if first_oi > 0 else 0.0
        
        today_vol = strike_daily.iloc[-1][vol_col]
        num_days = len(strike_daily)
        avg_vol = total_volume / num_days if num_days > 0 else 0
        rvol = round(today_vol / avg_vol, 2) if avg_vol > 0 else 0.0
        
        delta_sq_oi = 0
        if num_days >= 2:
            today_oi_change = strike_daily.iloc[-1][oi_col] - strike_daily.iloc[-2][oi_col]
            yesterday_oi_change = strike_daily.iloc[-2][oi_col] - (strike_daily.iloc[-3][oi_col] if num_days >= 3 else strike_daily.iloc[-2][oi_col])
            delta_sq_oi = today_oi_change - yesterday_oi_change

        exp_volumes = group.groupby(exp_col)[vol_col].sum()
        top_exp = exp_volumes.idxmax() if not exp_volumes.empty else "N/A"
        
        results.append({
            'Strike': strike, 'Type': opt_type, 'Top Expiration': top_exp, 'Total Volume': total_volume,
            'Start OI': first_oi, 'End OI': last_oi, 'Δ OI': net_oi_change,
            'Vol/OI': vol_oi_ratio, 'RVOL': rvol, 'Δ² OI': delta_sq_oi
        })
    p2 = True

    print(f"Results list size: {len(results)}")
    results_df = pd.DataFrame(results)

    top_vol = results_df.sort_values(by='Total Volume', ascending=False).head(15)
    results_df['Abs_OI'] = results_df['Δ OI'].abs()
    top_oi = results_df.sort_values(by='Abs_OI', ascending=False).drop(columns=['Abs_OI']).head(15)
    p3 = True
    print(f"Top Vol Size: {len(top_vol)}, Top OI size: {len(top_oi)}")
    
    try:
        out_ws = wb.worksheet("5-Day Flow Ledger")
    except:
        out_ws = wb.add_worksheet(title="5-Day Flow Ledger", rows=100, cols=10)
    
    print("Clearing Output Ledger tab...")

except Exception as e:
    print(f"EXCEPTION HIT: {e}")

print(f"P1: {p1}, P2: {p2}, P3: {p3}")
