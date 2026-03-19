import json

with open("nexus_spy_profile.json", "r") as f:
    data = json.load(f)

print(f"Magnet: {data.get('magnet')}")
print(f"Zero Gamma: {data.get('zero_gamma')}")
print(f"First Struct Magnet: {data['gex_structure'][0].get('volume_poc_strike')}")
print(f"First Struct Zero: {data['gex_structure'][0].get('gex_flip_point')}")
