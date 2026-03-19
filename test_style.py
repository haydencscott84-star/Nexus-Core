import streamlit as st
import pandas as pd
df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
st.dataframe(df.style.set_table_styles([{"selector": "th", "props": [("font-weight", "bold"), ("font-size", "20px")]}]))
