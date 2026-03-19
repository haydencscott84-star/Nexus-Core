import pandas as pd
import re

def compute_wall_colors(col):
    colors = []
    prev_val = None
    prev_color = ''
    # col is assumed to be the reversed series if we apply to df.iloc[::-1]
    # We should iterate in chronological order, which is reversed of col if col is oldest last...
    # Better yet, let's just use the index of the original dataframe
    
    # We will pass the chronological series
    
    for val in col:
        color = ''
        try:
            val_str = str(val)
            # Match the first dollar amount
            m = re.search(r'\$?([0-9,]+(?:\.[0-9]+)?)', val_str)
            if m:
                current_val = float(m.group(1).replace(',', ''))
                if prev_val is None:
                    color = ''
                elif current_val > prev_val:
                    color = 'background-color: rgba(38, 166, 91, 0.15);'
                    prev_color = color
                elif current_val < prev_val:
                    color = 'background-color: rgba(231, 76, 60, 0.15);'
                    prev_color = color
                else:
                    color = prev_color # Keep the previous color if unchanged
                prev_val = current_val
            else:
                color = prev_color
        except Exception:
            color = prev_color
        colors.append(color)
    return colors

df = pd.DataFrame({'Wall': ['$6650', '$6630', '$6630', '$6710']})
print("Chronological:")
print(compute_wall_colors(df['Wall']))

