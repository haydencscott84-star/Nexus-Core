import json
with open("local_orats_dump.json", "r") as f:
    d = json.load(f)
    print(d.get("data", [])[0])
