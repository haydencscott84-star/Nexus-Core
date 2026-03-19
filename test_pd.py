import pandas as pd
df = pd.DataFrame({'strike': ['4000', '4100', '4200'], 'gamma': ['0.1', '0.2', '0.3']})
try:
    df_filtered = df[(df['strike'] >= 4050.0)]
    print("Filter succeeded! Length:", len(df_filtered))
    print(df_filtered)
except Exception as e:
    print("Filter failed:", type(e), e)

# Test 2: If we convert first
df['strike'] = pd.to_numeric(df['strike'])
df_filtered2 = df[(df['strike'] >= 4050.0)]
print("Filter 2 length:", len(df_filtered2))
