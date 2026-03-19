import pandas as pd
import sys

filename = sys.argv[1]
with open(f"/root/{filename}", "r") as f:
    lines = f.readlines()

new_code = ""
for line in lines:
    if "out_ws.clear()" in line:
        new_code += "        print('DATA_EXTRACT:', top_vol[['Strike', 'Type', 'Total Volume', 'Start OI', 'Vol/OI', 'RVOL']].head(10))\n"
        new_code += "        print('TOP OI EXTRACT:', top_oi[['Strike', 'Type', 'Total Volume', 'Start OI', 'Vol/OI', 'RVOL']].head(10))\n"
        new_code += "        sys.exit(0)\n"
    new_code += line

try:
    exec(new_code)
    # The script defines the function, we need to call it!
    exec("update_google_sheet_ledger()")
except Exception as e:
    print(e)
