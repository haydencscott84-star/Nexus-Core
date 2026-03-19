import json

# Mock Data from Server
walls_ctx = {
    "SPX": {
        "6925.0": {"delta": -1247595181.267252},
        "7000.0": {"delta": 4377782946.817876},
        "6950.0": {"delta": 2124203009.060985}
    }
}

strike = 7000.0 # Float from profile
spx_walls = walls_ctx.get("SPX", {})

keys_to_try = [str(strike), str(int(strike)) if strike.is_integer() else str(strike), f"{strike:.1f}"]
print(f"Trying Keys for {strike}: {keys_to_try}")

found = None
for k in keys_to_try:
    if k in spx_walls: found = spx_walls[k]; break

print(f"Result: {found}")
if found:
    v = abs(found['delta'])
    if v >= 1e9: print(f"Format: ${v/1e9:.1f}B")
