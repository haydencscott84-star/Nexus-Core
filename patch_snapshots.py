import re
with open("/root/analyze_snapshots.py", "r") as f: content = f.read()

target = """    # [FIX] MAGNET = VOLUME POC (Not GEX)
    # Standardized Definition: Strike with Max Total Volume (Calls + Puts)
    vol_profile = spy_df.groupby('strike')['vol'].sum()
    if not vol_profile.empty:
        results['volume_poc'] = vol_profile.idxmax()
    else:
        results['volume_poc'] = 0.0"""

replacement = """    # [FIX] MAGNET = VOLUME POC (Not GEX)
    # Standardized Definition: Strike with Max Total Volume (Calls + Puts)
    # Filter out anomalous tail-risk strikes (e.g. $535) and far-dated rolls
    try:
        poc_df = spy_df.copy()
        if 'dte' in poc_df.columns:
            poc_df = poc_df[poc_df['dte'] <= 14]
        
        valid_range = spot * 0.10
        poc_df = poc_df[poc_df['strike'].between(spot - valid_range, spot + valid_range)]
        
        vol_profile = poc_df.groupby('strike')['vol'].sum()
        if not vol_profile.empty:
            results['volume_poc'] = vol_profile.idxmax()
        else:
            results['volume_poc'] = 0.0
    except:
        results['volume_poc'] = 0.0"""

new_content = content.replace(target, replacement)
with open("/root/analyze_snapshots.py", "w") as f: f.write(new_content)
print("Patch applied.")
