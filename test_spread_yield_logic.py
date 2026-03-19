
# Spread Yield Logic Verification

def calculate_yield(credit, width):
    if width == 0: return 0
    return (credit / width) * 100

def get_yield_quality(yield_pct):
    if yield_pct > 30:
        return "HIGH QUALITY (GREEN)"
    elif yield_pct >= 20:
        return "ACCEPTABLE (YELLOW)"
    else:
        return "POOR (RED)"

def test_spread(case_name, short_strike, long_strike, credit):
    width = abs(short_strike - long_strike)
    yield_pct = calculate_yield(credit, width)
    quality = get_yield_quality(yield_pct)
    
    print(f"--- {case_name} ---")
    print(f"Strikes: {short_strike}/{long_strike} (Width: ${width:.2f})")
    print(f"Credit:  ${credit:.2f}")
    print(f"Yield:   {yield_pct:.1f}%")
    print(f"Rating:  {quality}")
    print(f"Target Check (>30%): {'PASS' if yield_pct > 30 else 'FAIL'}")
    print("-" * 30)

if __name__ == "__main__":
    print("=== TESTING YIELD LOGIC ===\n")
    
    # CASE 1: The User's Example (High Quality)
    # "On a $5 wide spread, look for $1.50+ Credit."
    test_spread("User Example (Target)", 580, 585, 1.55)
    
    # CASE 2: Acceptable
    test_spread("Acceptable Yield", 580, 585, 1.25) # 25%
    
    # CASE 3: Poor
    test_spread("Poor Yield", 580, 585, 0.50) # 10%
    
    # CASE 4: Edge Case (Exact 30%)
    test_spread("Borderline (30%)", 500, 510, 3.00)
    
    # CASE 5: Deep ITM / Inverted (Shouldn't happen with strict scanning but good to test math)
    # Logic holds regardless of strike placement as long as Width is absolute.
    test_spread("Wide Spread High Credit", 550, 600, 20.00) # 40%
