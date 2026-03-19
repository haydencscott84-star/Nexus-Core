import pandas as pd
from tabulate import tabulate
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def analyze_5_day_institutional_flow():
    """
    Fetches options data, isolates the last 5 trading days, and ranks the strikes 
    with the highest Volume and largest Net Change in Open Interest.
    """
    CREDENTIALS_FILE = "tribal-flux-476216-c0-70e4f946eb77.json"
    SHEET_ID = '1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg'
    
    print("Authenticate and load data from Google Sheets ('Historical Data')...")
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        wb = client.open_by_key(SHEET_ID)
        ws = wb.worksheet("Historical Data")
        data = ws.get_all_values()
        
        if not data or len(data) < 2:
            print("No data found in Historical Data tab.")
            return
            
        headers = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)
    except Exception as e:
        print(f"Error loading data: {e}. Please check your tab name or connection.")
        return

    # Ensure column names match your sheet
    date_col = 'Trade Date'
    strike_col = 'Strike'
    type_col = 'Type'
    oi_col = 'Open Interest'
    vol_col = 'Volume'

    # Convert columns to correct types for accurate aggregation
    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
    df[strike_col] = pd.to_numeric(df[strike_col], errors='coerce')
    df[oi_col] = pd.to_numeric(df[oi_col], errors='coerce').fillna(0)
    df[vol_col] = pd.to_numeric(df[vol_col], errors='coerce').fillna(0)
    
    df = df.dropna(subset=[date_col, strike_col])

    # 2. Isolate the Last 5 Trading Days
    unique_dates = sorted(df[date_col].dt.date.unique())
    if len(unique_dates) == 0:
        print("No valid trading dates found.")
        return
        
    last_5_days = unique_dates[-5:]
    df_filtered = df[df[date_col].dt.date.isin(last_5_days)].copy()

    # Optimiztion: Because a single Strike/Type can have multiple Expirations on a single Trade Date,
    # we first need to sum the OI and Volume per Trade Date before querying the time-series change.
    daily_aggregated = df_filtered.groupby([date_col, strike_col, type_col], as_index=False).agg({
        vol_col: 'sum',
        oi_col: 'sum'
    })

    # 3. Calculate 5-Day Metrics (Volume Sum & Net OI Change)
    grouped = daily_aggregated.groupby([strike_col, type_col])
    
    results = []
    for (strike, opt_type), group in grouped:
        group = group.sort_values(by=date_col)
                    
        # Total volume traded over the 5 days
        total_volume = group[vol_col].sum()
        
        # Net change in OI (Last Day OI - First Day OI of the 5-day window)
        first_oi = group.iloc[0][oi_col]
        last_oi = group.iloc[-1][oi_col]
        net_oi_change = last_oi - first_oi
        
        results.append({
            'Strike': strike,
            'Type': opt_type,
            'Total 5-Day Volume': total_volume,
            'Starting OI': first_oi,
            'Ending OI': last_oi,
            'Δ OI (Net Change)': net_oi_change
        })

    results_df = pd.DataFrame(results)

    # 4. Filter and Rank
    # We will expand it slightly to top 10 to give a better ledger view
    top_volume = results_df.sort_values(by='Total 5-Day Volume', ascending=False).head(10)
    
    results_df['Abs_Δ_OI'] = results_df['Δ OI (Net Change)'].abs()
    top_oi_change = results_df.sort_values(by='Abs_Δ_OI', ascending=False).drop(columns=['Abs_Δ_OI']).head(10)

    # 5. Output to Terminal
    s_date = last_5_days[0].strftime('%Y-%m-%d')
    e_date = last_5_days[-1].strftime('%Y-%m-%d')
    print("\n" + "="*80)
    print(f" 🔥 TOP 10 MOST TRADED STRIKES (Last {len(last_5_days)} Days: {s_date} to {e_date})")
    print("="*80)
    print(tabulate(top_volume, headers='keys', tablefmt='pretty', showindex=False, floatfmt=".0f"))

    print("\n" + "="*80)
    print(" 🧱 LARGEST INSTITUTIONAL SHIFTS (Top 10 Net Change in OI)")
    print("="*80)
    print(tabulate(top_oi_change, headers='keys', tablefmt='pretty', showindex=False, floatfmt=".0f"))

if __name__ == "__main__":
    analyze_5_day_institutional_flow()
