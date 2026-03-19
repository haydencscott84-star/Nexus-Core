import pexpect
import sys

script = """
import sys
import pandas as pd
sys.path.append('/root')

from analyze_snapshots import load_unified_data, calculate_market_structure_metrics
df = load_unified_data(5)
spy_df = df[df['ticker'] == 'SPY'].copy()
spot = spy_df[spy_df['underlying_price'] > 10.0]['underlying_price'].iloc[-1]

latest_date = spy_df['date'].max()
print(f"Latest Date: {latest_date}")
spy_df_fil = spy_df[spy_df['date'] == latest_date]

poc_df = spy_df_fil.copy()
poc_df['dte'] = pd.to_numeric(poc_df['dte'], errors='coerce')
poc_df = poc_df[poc_df['dte'] <= 14]

valid_range = spot * 0.10
poc_df = poc_df[poc_df['strike'].between(spot - valid_range, spot + valid_range)]

vol_profile = poc_df.groupby('strike')['vol'].sum()
print("Top Valid Strikes:")
print(vol_profile.sort_values(ascending=False).head(5))
"""

with open("tmp_poc_fix.py", "w") as f:
    f.write(script)

child = pexpect.spawn('scp -o StrictHostKeyChecking=no tmp_poc_fix.py root@<YOUR_VPS_IP>:/root/')
child.expect('password:')
child.sendline('<YOUR_VPS_PASSWORD>')
child.expect(pexpect.EOF)

child2 = pexpect.spawn('ssh -o StrictHostKeyChecking=no root@<YOUR_VPS_IP> "python3 /root/tmp_poc_fix.py"')
child2.expect('password:')
child2.sendline('<YOUR_VPS_PASSWORD>')
child2.expect(pexpect.EOF)
print(child2.before.decode('utf-8'))
