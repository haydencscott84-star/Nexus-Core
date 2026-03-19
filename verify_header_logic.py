# Verify Header Logic
# Simulates the logic inside nexus_spreads.py account_data_loop

def verify_header(eq, pl, exp):
    print(f"Testing with EQ=${eq}, P/L=${pl}, EXP=${exp}")
    
    # Logic from nexus_spreads.py
    pl_pct = (pl / eq * 100) if eq != 0 else 0.0
    exp_pct = (exp / eq * 100) if eq != 0 else 0.0
    
    display_str = f"P/L: ${pl:.0f} ({pl_pct:+.1f}%) | EXP: ${exp/1000:.1f}K ({exp_pct:.1f}%)"
    print(f"Result: {display_str}")
    
    # Assertions
    if "EQ:" in display_str:
        print("FAIL: Equity is still visible!")
    else:
        print("PASS: Equity is hidden.")
        
    if "%" in display_str:
        print("PASS: Percentages are shown.")
    else:
        print("FAIL: Percentages missing.")

# Test Cases
verify_header(100000, 500, 25000) # Normal
verify_header(100000, -1500, 50000) # Loss
verify_header(0, 0, 0) # Zero Equity (Edge Case)
