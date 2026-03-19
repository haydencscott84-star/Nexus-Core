
try:
    from nexus_sheets_bridge import run_update
    print("Forcing Manual Update...")
    run_update("MANUAL_DEBUG")
    print("Update Complete.")
except Exception as e:
    print(f"Error: {e}")
