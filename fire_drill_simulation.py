from alert_manager import TradeGuardian, send_discord_alert
import alert_manager
import time

print("🔥 STARTING FIRE DRILL SIMULATION 🔥")

# 1. Initialize Guardian
print("[*] Initializing Guardian...")
guardian = TradeGuardian()

# 2. Mock Data
print("[*] Mocking Market Data: SPY = $695.00 (Above $689 Threshold)")
guardian.update_price(695.00)
guardian.sim_4h_close = 695.00 # Force the 4H close condition

# 3. Ensure DRY_RUN
alert_manager.DRY_RUN = True
print("[*] DRY_RUN Mode: ENABLED")

# 4. Run Check
print("[*] Running Guardian Check...")
guardian.check(force=True)

# 5. Send Confirmation
print("[*] Sending Discord Confirmation...")
send_discord_alert("FIRE DRILL", "🚨 FIRE DRILL: Test Alert. System is functioning.", 0x00FF00)

print("✅ FIRE DRILL COMPLETE.")
