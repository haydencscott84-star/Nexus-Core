import json

with open("nexus_spy_profile.json", "r") as f:
    data = json.load(f)

print(json.dumps(data['gex_structure'][0], indent=2))
