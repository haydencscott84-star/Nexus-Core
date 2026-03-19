import re

with open("viewer_dash_nexus.py", "r") as f:
    content = f.read()

old_block = """                    # [NEW] Synchronous Push to Supabase for Streamlit SPY Profiler
                    supabase = get_supabase_client()
                    if supabase:
                        try:
                            import json
                            with open("nexus_spy_profile.json", "r") as f:
                                native_spy_state = json.load(f)
                            supabase.table("nexus_profile").upsert({"id": "spy_latest", "data": native_spy_state}).execute()
                        except Exception as e:
                            self.call_from_thread(self.log_msg, f"SUPABASE ERROR: {e}")"""

new_block = """                    # [NEW] Native HTTP Post to Supabase (Bypassing SDK Int64 limits)
                    try:
                        import os
                        import requests
                        import json
                        
                        SUPABASE_URL = os.getenv('SUPABASE_URL')
                        SUPABASE_KEY = os.getenv('SUPABASE_KEY')
                        
                        if SUPABASE_URL and SUPABASE_KEY:
                            with open("nexus_spy_profile.json", "r") as f:
                                native_spy_state = json.load(f)
                                
                            payload = {
                                "id": "spy_latest",
                                "data": native_spy_state
                            }
                            
                            headers = {
                                "apikey": SUPABASE_KEY,
                                "Authorization": f"Bearer {SUPABASE_KEY}",
                                "Content-Type": "application/json",
                                "Prefer": "resolution=merge-duplicates"
                            }
                            
                            url = f"{SUPABASE_URL}/rest/v1/nexus_profile"
                            resp = requests.post(url, json=payload, headers=headers, timeout=5)
                            # self.call_from_thread(self.log_msg, f"SUPABASE HTTP POST: {resp.status_code}")
                    except Exception as e:
                        self.call_from_thread(self.log_msg, f"SUPABASE HTTP ERROR: {e}")"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("viewer_dash_nexus.py", "w") as f:
        f.write(content)
    print("Patched viewer_dash_nexus.py successfully!")
else:
    print("WARNING: Could not find old block in viewer_dash_nexus.py")

with open("remote_viewer_dash_nexus.py", "r") as f:
    content = f.read()

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("remote_viewer_dash_nexus.py", "w") as f:
        f.write(content)
    print("Patched remote_viewer_dash_nexus.py successfully!")
else:
    print("WARNING: Could not find old block in remote_viewer_dash_nexus.py")
