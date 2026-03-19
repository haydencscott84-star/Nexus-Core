import pandas as pd
import numpy as np
import datetime
import math

def analyze_gamma_exposure(strikes_data, spot_price, target_date_str):
    summary_stats = {
        'total_gamma': 0, 'spot_gamma': 0, 'max_pain_strike': None, 'volume_poc_strike': None,
        'volume_poc_sent': 'N/A', 'short_gamma_wall_above': None, 'short_gamma_wall_below': None,
        'long_gamma_wall_above': None, 'long_gamma_wall_below': None,
        'pc_ratio_volume': None, 'pc_ratio_oi': None, 'gex_flip_point': None
    }
    if not strikes_data: return summary_stats
    try:
        df = pd.DataFrame(strikes_data)
        if 'expirDate' not in df.columns: return summary_stats
        
        df['expirDate_dt'] = pd.to_datetime(df['expirDate']).dt.date
        target_dt = pd.to_datetime(target_date_str).date()
        df_target = df[df['expirDate_dt'] == target_dt].copy()
        
        if df_target.empty: return summary_stats

        cols = ['gamma', 'callOpenInterest', 'putOpenInterest', 'callVolume', 'putVolume', 'strike']
        for c in cols: df_target[c] = pd.to_numeric(df_target[c], errors='coerce').fillna(0)
        
        call_gex = df_target['callOpenInterest'] * 100 * df_target['gamma']
        put_gex = (df_target['putOpenInterest'] * 100 * df_target['gamma'])
        total_gex_units = (call_gex - put_gex) 
        
        summary_stats['total_gamma'] = total_gex_units.sum() * (spot_price**2) * 0.01
        df_target['total_gamma_exp'] = total_gex_units * (spot_price**2) * 0.01
        
        df_target['total_vol'] = df_target['callVolume'] + df_target['putVolume']
        if df_target['total_vol'].sum() > 0:
            poc = df_target.loc[df_target['total_vol'].idxmax()]
            summary_stats['volume_poc_strike'] = float(poc['strike'])
            summary_stats['volume_poc_sent'] = 'C' if poc['callVolume'] > poc['putVolume'] else 'P'

        # [NEW] P/C Ratios
        total_call_vol = df_target['callVolume'].sum()
        total_put_vol = df_target['putVolume'].sum()
        if total_call_vol > 0:
            summary_stats['pc_ratio_volume'] = total_put_vol / total_call_vol
        
        total_call_oi = df_target['callOpenInterest'].sum()
        total_put_oi = df_target['putOpenInterest'].sum()
        if total_call_oi > 0:
            summary_stats['pc_ratio_oi'] = total_put_oi / total_call_oi

        # Walls & Flip Point
        sig_gex = df_target[df_target['total_gamma_exp'].abs() > 1.0].copy()
        
        if not sig_gex.empty:
            short_gex = sig_gex[sig_gex['total_gamma_exp'] < 0]
            if not short_gex.empty:
                above = short_gex[short_gex['strike'] > spot_price]; below = short_gex[short_gex['strike'] < spot_price]
                if not above.empty: 
                    row = above.loc[above['total_gamma_exp'].idxmin()]
                    summary_stats['short_gamma_wall_above'] = float(row['strike'])
                if not below.empty: 
                    row = below.loc[below['total_gamma_exp'].idxmin()]
                    summary_stats['short_gamma_wall_below'] = float(row['strike'])
            
            long_gex = sig_gex[sig_gex['total_gamma_exp'] > 0]
            if not long_gex.empty:
                above = long_gex[long_gex['strike'] > spot_price]; below = long_gex[long_gex['strike'] < spot_price]
                if not above.empty: 
                    row = above.loc[above['total_gamma_exp'].idxmax()]
                    summary_stats['long_gamma_wall_above'] = float(row['strike'])
                if not below.empty: 
                    row = below.loc[below['total_gamma_exp'].idxmax()]
                    summary_stats['long_gamma_wall_below'] = float(row['strike'])

        # Fallback for Short Wall Above if missing (Blue Sky)
        if summary_stats['short_gamma_wall_above'] is None and not sig_gex.empty:
             pos_above = sig_gex[(sig_gex['strike'] > spot_price) & (sig_gex['total_gamma_exp'] > 0)]
             if not pos_above.empty:
                 row = pos_above.loc[pos_above['total_gamma_exp'].idxmax()]
                 summary_stats['short_gamma_wall_above'] = float(row['strike']) # Use Call Wall as proxy

        # Flip Point
        df_sorted = df_target.sort_values('strike')
        strikes = df_sorted['strike'].values
        gammas = df_sorted['total_gamma_exp'].values
        for i in range(len(strikes) - 1):
            g1 = gammas[i]; g2 = gammas[i+1]
            if (g1 > 0 and g2 < 0) or (g1 < 0 and g2 > 0):
                if abs(g1) < abs(g2): flip = strikes[i]
                else: flip = strikes[i+1]
                if abs(flip - spot_price) < (spot_price * 0.05):
                    summary_stats['gex_flip_point'] = float(flip)
                    break
        
        # Max Pain
        strikes_u = df_target['strike'].unique()
        if len(strikes_u) > 0:
            total_values = []
            sample = [s for s in strikes_u if s % 5 == 0]
            for px in sample:
                val = ((px - df_target['strike']).clip(lower=0) * df_target['callOpenInterest']).sum() + ((df_target['strike'] - px).clip(lower=0) * df_target['putOpenInterest']).sum()
                total_values.append((px, val))
            if total_values: summary_stats['max_pain_strike'] = float(min(total_values, key=lambda x: x[1])[0])

        return summary_stats
    except Exception as e:
        return summary_stats
