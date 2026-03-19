import json
import os

files = ["nexus_walls_context.json"]
for fn in files:
    if os.path.exists(fn):
        try:
            with open(fn, "r") as f:
                data = json.load(f)
            
            # Manual Patch for SPX 6840 (Put Wall)
            # derived from CSV: OI ~40k, Delta ~-0.35 -> $1B range.
            # Precision doesn't matter as much as magnitude for now.
            # Using $950M (~40k * 0.35 * 6800 * 100)
            if "SPX" in data:
                data["SPX"]["6840.0"] = {
                    "delta": 950000000.0,
                    "oi_delta": 0,
                    "status": "HOTFIX_WALL"
                }
                print("✅ Patched 6840.0 into SPX")
            
            with open(fn, "w") as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            print(f"Error: {e}")
