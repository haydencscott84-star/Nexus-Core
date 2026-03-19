
import os
import re

target_file = "/root/nexus_debit.py"
print(f"Applying Selection Fix to {target_file}...")

# 1. New populate_debit_chain with KEY generation
new_populate = """    def populate_debit_chain(self, chain_data, width, target_strike=0.0, ivr=0.0):
        try:
            table = self.query_one("#chain_table", DataTable)
            table.clear(columns=True)
            table.add_columns("EXPIRY", "DTE", "LONG (ITM)", "SHORT (OTM)", "DEBIT", "% TO B/E", "PROB. ADJ.", "MAX ROC %", "B/E", "WIN %")
            
            if not chain_data:
                self.log_msg("No spreads returned. Check Strike/Width.")
                return

            cur_price = getattr(self, "current_spy_price", 0.0)
            if cur_price <= 0: cur_price = 0.01
            
            # Prob Adj Logic
            if ivr < 30: prob_txt = "[bold green]Cheap (Low IV)[/]"
            elif ivr > 50: prob_txt = "[bold red]Expensive[/]"
            else: prob_txt = "Neutral"

            for s in chain_data:
                try:
                    ask_short = float(s.get("ask_short", 0))
                    bid_long = float(s.get("bid_long", 0))
                    
                    debit = ask_short - bid_long
                    if debit <= 0: debit = 0.01 
                    
                    width_val = abs(float(s["short"]) - float(s["long"]))
                    max_profit_theo = width_val - debit
                    max_roc = (max_profit_theo / debit) * 100 if debit > 0 else 0
                    
                    l_strike = float(s["short"]) 
                    s_strike = float(s["long"])
                    
                    is_call = l_strike < s_strike
                    if is_call: 
                        be = l_strike + debit
                        strat_type = 'bull'
                    else: 
                        be = l_strike - debit
                        strat_type = 'bear'
                    
                    # Calc Dist %
                    if cur_price > 1.0:
                        if is_call:
                            dist_pct = ((be - cur_price) / cur_price) * 100
                        else:
                            dist_pct = ((cur_price - be) / cur_price) * 100
                            
                        if dist_pct <= 0: dist_style = "[bold green]"
                        elif dist_pct < 0.5: dist_style = "[bold yellow]"
                        else: dist_style = "[white]"
                        
                        dist_str = f"{dist_style}{dist_pct:.2f}%[/]"
                    else:
                        dist_str = "---"

                    roc_style = "bold green" if max_roc > 80 else "bold yellow"
                    
                    # Win % (PoP Logic)
                    win_pct = 0.0
                    try:
                        k_float = f"{s['expiry']}|{float(l_strike):.1f}"
                        k_int = f"{s['expiry']}|{int(l_strike)}"
                        
                        omap = getattr(self, "orats_map", {})
                        orats_data = omap.get(k_float)
                        if not orats_data:
                            orats_data = omap.get(k_int)
                        
                        if orats_data:
                            if isinstance(orats_data, float): orats_data = {'delta': orats_data, 'iv': 0.0}
                            iv = orats_data.get('iv', 0.0)
                            win_pct = self.calculate_pop(cur_price, be, float(s['dte']), iv, strat_type)
                    except: pass

                    row = [
                        s["expiry"], str(s["dte"]),
                        f"{l_strike:.1f}", f"{s_strike:.1f}",
                        f"${debit:.2f}",
                        dist_str,
                        prob_txt,
                        f"[bold {roc_style}]{max_roc:.1f}%[/]",
                        f"${be:.2f}",
                        f"{win_pct:.0f}%"
                    ]
                    
                    # [FIX] Generate Key via String
                    # Key: Expiry|Long|Short|Debit|Width|IsCall
                    row_key = f"{s['expiry']}|{l_strike}|{s_strike}|{debit}|{width_val}|{is_call}"
                    
                    table.add_row(*row, key=row_key)
                    
                except: continue
                
        except Exception as e:
            self.log_msg(f"Chain Error: {e}")
"""

# 2. Inject Handler Logic
handler_code = """
    @on(DataTable.RowSelected, "#chain_table")
    def on_chain_selected(self, event: DataTable.RowSelected):
        try:
            row_key = event.row_key.value
            if not row_key or "|" not in row_key: return
            
            parts = row_key.split("|")
            if len(parts) < 6: return
            
            # Parse Key: Expiry|Long|Short|Debit|Width|IsCall
            expiry_str = parts[0] # YYYY-MM-DD
            long_strike = float(parts[1])
            short_strike = float(parts[2])
            debit = float(parts[3])
            width = float(parts[4])
            is_call = parts[5] == "True"
            
            # Format Expiry for OCC (YYYY-MM-DD -> YYMMDD)
            # Assumption: expiry_str is YYYY-MM-DD
            try:
                y, m, d = expiry_str.split("-")
                occ_date = f"{y[2:]}{m}{d}"
            except:
                self.log_msg("Date Parse Error")
                return

            # Format Strikes (00000000)
            def fmt_strike(p):
                return f"{int(p*1000):08d}"
            
            type_char = "C" if is_call else "P"
            root = "SPY" # Hardcoded for now based on context
            
            long_sym = f"{root}{occ_date}{type_char}{fmt_strike(long_strike)}"
            short_sym = f"{root}{occ_date}{type_char}{fmt_strike(short_strike)}"
            
            # Update State
            self.selected_spread = {
                "long_sym": long_sym,
                "short_sym": short_sym,
                "debit": debit,
                "width": width,
                "long_strike": long_strike,
                "short_strike": short_strike,
                "expiry": expiry_str,
                "is_call": is_call
            }
            
            # Update UI Panels (Right Side)
            # Labels: #selected_setup_lbl, #debit_cost_lbl, #tgt_profit_lbl, #max_roc_lbl, #stop_sys_lbl
            
            max_profit = width - debit
            roc = (max_profit / debit * 100) if debit > 0 else 0
            
            # Logic: Stop is approx 1% of strike (or debit based, but bot uses 1% strike)
            if is_call: stop_val = long_strike * 0.99
            else: stop_val = long_strike * 1.01
            
            setup_str = f"{'CALL' if is_call else 'PUT'} {long_strike}/{short_strike} ({expiry_str})"
            
            try:
                self.query_one("#selected_setup_lbl").update(f"[bold cyan]{setup_str}[/]")
                self.query_one("#debit_cost_lbl").update(f"[bold yellow]${debit:.2f}[/]")
                self.query_one("#tgt_profit_lbl").update(f"[bold green]${(debit * 1.5):.2f} (50%)[/]")
                self.query_one("#max_roc_lbl").update(f"[bold green]{roc:.0f}%[/]")
                self.query_one("#stop_sys_lbl").update(f"[bold red]${stop_val:.2f} (SPY)[/]")
                
                # Enable Button
                btn = self.query_one("#execute_btn")
                btn.disabled = False
                btn.variant = "success"
                
                self.recalc_totals()
                
            except Exception as ui_e:
                self.log_msg(f"UI Upd Error: {ui_e}")

        except Exception as e:
            self.log_msg(f"Sel Error: {e}")
"""

# Apply
with open(target_file, 'r') as f:
    content = f.read()

# Replace populate
# This is tricky with indentation. We'll verify indentation matches original.
# The original starts with 4 spaces. My string uses 4 spaces.
import re
# Regex to replace the entire function body? Risky.
# Better to replace by exact string match of the def line if possible, or just append the handler and replace the method.

# Strategy: 
# 1. Remove old populate_debit_chain method using explicit line range knows from cat or search.
# 2. Append new populate_debit_chain and handler at the end of the class (or file).
# Wait, it must be inside the class NexusDebit(App).
# The class ends around line 920.

# Safer Strategy: Use replace on the exact definition block if I can match it.
# Or, since I know the file content, I can read it all, find "def populate_debit_chain", find the next def, and replace the chunk.

start_marker = "    def populate_debit_chain"
end_marker = "    def on_qty_change" # This is usually the next method based on method map

p1 = content.find(start_marker)
p2 = content.find(end_marker)

if p1 != -1 and p2 != -1:
    print(f"Replacing chunk from {p1} to {p2}...")
    new_content = content[:p1] + new_populate + "\n" + handler_code + "\n" + content[p2:]
    
    with open(target_file, 'w') as f:
        f.write(new_content)
    print("Success!")
else:
    print("Could not locate method boundaries. Manual intervention required.")
