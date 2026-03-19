import sys

try:
    with open("gemini_market_auditor.py", "r") as f:
        content = f.read()

    # 1. Update send_discord_msg signature
    if "def send_discord_msg(text, color=None, message_id=None):" in content:
        content = content.replace(
            "def send_discord_msg(text, color=None, message_id=None):",
            "def send_discord_msg(text, color=None, message_id=None, fields=None):"
        )
        print("✅ Updated send_discord_msg signature")

    # 2. Update payload construction
    if '"color": color_val,' in content and '"fields": fields' not in content:
        content = content.replace(
            '"color": color_val,',
            '"color": color_val,\n            "fields": fields,'
        )
        print("✅ Updated send_discord_msg payload")

    # 3. Update send_alert signature
    if "def send_alert(self, text, color):" in content:
        content = content.replace(
            "def send_alert(self, text, color):",
            "def send_alert(self, text, color, fields=None):"
        )
        print("✅ Updated send_alert signature")

    # 4. Update send_alert call to send_discord_msg
    if "new_id = send_discord_msg(text, color=color, message_id=self.last_message_id)" in content:
        content = content.replace(
            "new_id = send_discord_msg(text, color=color, message_id=self.last_message_id)",
            "new_id = send_discord_msg(text, color=color, message_id=self.last_message_id, fields=fields)"
        )
        print("✅ Updated send_alert invocation")

    # 5. Inject Field Construction Logic before send_alert call in run_cycle
    # We look for the line: self.send_alert(msg_text, color=alert_color)
    injection_marker = "self.send_alert(msg_text, color=alert_color)"
    
    field_logic = """
            # --- CONSTRUCT DISCORD FIELDS ---
            discord_fields = []
            
            # Field 1: Position Core
            if direction != "NEUTRAL":
                pos_val = f"{direction} {ticker}\\nEntry: ${entry_price:.2f}"
                if grouped_spreads:
                    pos_val += f"\\n({len(grouped_spreads)} Spreads)"
                discord_fields.append({"name": "🎯 Position", "value": pos_val, "inline": True})
                
                # Field 2: Performance
                perf_val = f"P/L: {pos_pnl_pct:+.2f}%\\nAcct: {pnl_pct:+.2f}%"
                discord_fields.append({"name": "💰 Performance", "value": perf_val, "inline": True})
                
                # Field 3: Risk/Greeks
                greeks_val = f"Delta: {delta}\\nGamma: {gamma}\\nTheta: {theta}"
                discord_fields.append({"name": "⚡ Greeks", "value": greeks_val, "inline": True})

            self.send_alert(msg_text, color=alert_color, fields=discord_fields)
    """

    if injection_marker in content and "discord_fields" not in content:
        content = content.replace(
            injection_marker,
            field_logic.strip()
        )
        print("✅ Injected Field Construction Logic")

    with open("gemini_market_auditor.py", "w") as f:
        f.write(content)
    
    print("🚀 Patch Applied Successfully")

except Exception as e:
    print(f"❌ Patch Failed: {e}")
