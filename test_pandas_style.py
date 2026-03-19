import pandas as pd
import re

def style_wall(s):
    colors = []
    prev_val = None
    prev_color = ''
    
    # Let's print the actual values passed in s to see the order
    print("Received s order:")
    for val in s:
        print(val)
        
    for val in s[::-1]: # assumes oldest to newest
        color = ''
        try:
            val_str = str(val)
            m = re.search(r'\$?([0-9,]+(?:\.[0-9]+)?)', val_str)
            if m:
                current_val = float(m.group(1).replace(',', ''))
                if prev_val is None:
                    color = ''
                elif current_val > prev_val:
                    color = 'GREEN'
                elif current_val < prev_val:
                    color = 'RED'
                else:
                    color = prev_color
                
                prev_val = current_val
                prev_color = color if color != '' else prev_color
            else:
                color = prev_color
        except Exception as e:
            color = prev_color
            
        colors.append(color)
        
    res = colors[::-1]
    print("Returned colors order:")
    print(res)
    return res

df_regime = pd.DataFrame({
    'Call Wall': ['$6710', '$6710', '$6725', '$6710', '$6710'], # 384, 385, 386, 387, 388
    'Put Wall':  ['$6675', '$6675', '$6675', '$6675', '$6685']  # 384, 385, 386, 387, 388
})

regime_styled = df_regime.iloc[::-1].style.apply(style_wall, subset=['Call Wall', 'Put Wall'], axis=0)
regime_styled._compute()

