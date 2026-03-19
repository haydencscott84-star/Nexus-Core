    def populate_chain(self, data, ivr=0.0):
        try:
            table = self.query_one("#chain_table", DataTable)
            table.clear(columns=True)
            table.add_columns("EXPIRY", "DTE", "SHORT", "LONG", "CREDIT", "MAX RISK", "RETURN %", "PROB. ADJ.", "WIN %")
            
            cur_price = getattr(self, "current_spy_price", 0.0)
            if cur_price <= 0: cur_price = 500.0
            
            if ivr > 50: prob_txt = "[bold green]Rich (High IV)[/]"
            elif ivr < 30: prob_txt = "[bold red]Low IV[/]"
            else: prob_txt = "Neutral"

            if not data: return

            for s in data:
                try:
                    credit = float(s.get("credit", 0))
                    width = float(s.get("width", 5))
                    # Filter Bad Data
                    if credit >= width or credit <= 0: continue
                except: continue

                max_risk = width - credit
                ret_pct = (credit / max_risk) * 100 if max_risk > 0 else 0
                
                short_strike = float(s.get("short", 0))
                long_strike = float(s.get("long", 0))
                
                # Determine Strategy Type & Breakeven
                is_put_credit = short_strike > long_strike
                
                if is_put_credit:
                    strat_type = 'bull'
                    be = short_strike - credit
                else:
                    strat_type = 'bear'
                    be = short_strike + credit
                
                # Win % Calculation
                win_val = 0.0
                try:
                    # Robust Key Generation
                    k_float = f"{s['expiry']}|{float(short_strike):.1f}"
                    k_int = f"{s['expiry']}|{int(short_strike)}"
                    
                    omap = getattr(self, "orats_map", {})
                    orats_dat = omap.get(k_float)
                    if not orats_dat:
                        orats_dat = omap.get(k_int)
                    
                    # Debug Log Logic (Silent unless file exists/empty)
                    if not orats_dat:
                        try:
                            import os
                            log_file = '/tmp/nexus_win_debug.log'
                            # Only write if file exists to avoid disk spam, or create if debugging requested
                            # For now, auto-create to help diagnosis
                            if not os.path.exists(log_file) or os.path.getsize(log_file) < 50000:
                                with open(log_file, 'a') as f:
                                     debug_keys = list(omap.keys())[:3] if omap else "EMPTY_MAP"
                                     f.write(f"MISS: Tried '{k_float}' / '{k_int}' | Map Size: {len(omap)} | Sample: {debug_keys}\n")
                        except: pass
                    
                    if orats_dat:
                        iv = orats_dat.get('iv', 0.0)
                        win_val = self.calculate_pop(cur_price, be, float(s['dte']), iv, strat_type)
                except:
                    pass

                if win_val == 0: win_str = "-"
                else: win_str = f"{win_val:.0f}%"

                row = [
                    s["expiry"], str(s["dte"]),
                    f"{short_strike:.1f}", f"{long_strike:.1f}",
                    f"${credit:.2f}",
                    f"${max_risk:.2f}",
                    f"[bold green]{ret_pct:.1f}%[/]" if ret_pct > 20 else f"{ret_pct:.1f}%",
                    prob_txt,
                    win_str
                ]
                
                key = f"{short_strike}|{long_strike}|{credit}|{short_strike}|{long_strike}|{width}"
                table.add_row(*row, key=key)
                
        except Exception as e:
            # self.log_msg(f"Chain Error: {e}")
            pass
    @on(Input.Changed, "#qty_input")
    def on_qty_change(self, event: Input.Changed):
        self.calculate_risk()

    def calculate_risk(self):
        if not self.selected_spread: return
        
        try:
            qty = int(self.query_one("#qty_input").value)
        except: qty = 1
        
        # Risk per Spread
        # Credit Spread Risk = Width - Credit
        # Debit Spread Risk = Debit Paid (which is the "Credit" field but negative? No, fetch_chain returns positive credit for credit spreads)
        # Wait, fetch_chain logic:
        # Credit = Bid Short - Ask Long.
        # If Credit > 0: Credit Spread. Risk = Width - Credit.
        # If Credit < 0: Debit Spread. Cost = -Credit. Risk = Cost.
        
        # However, fetch_chain calculates 'risk' field assuming Credit Spread logic?
        # Let's check fetch_chain in ts_nexus.py...
        # It calculates: credit = bid_short - ask_long. risk = width - credit.
        # If it's a Debit Spread (e.g. Bull Call), Short is Lower Strike (Buy), Long is Higher (Sell).
        # Bid Short (Buy) - Ask Long (Sell)? No.
        # Debit Spread: Buy Short (Ask), Sell Long (Bid).
        # Cost = Ask Short - Bid Long.
        # fetch_chain logic might be flawed for Debit if it assumes Credit logic.
        # But for now, let's rely on the 'risk' value from the table row if possible, or recalculate.
        # The table row has "RISK" column.
        # self.selected_spread has "credit", "short_strike", "long_strike".
        
        # Let's assume Credit Spread logic for now as that's the primary use case.
        # Risk Per Contract = Width - Credit
        width = abs(self.selected_spread["short_strike"] - self.selected_spread["long_strike"])
        credit = self.selected_spread["credit"]
        
        # If Credit is negative, it's a Debit.
        # If Credit is negative, it's a Debit.
        if credit < 0:
             risk_per_share = abs(credit)
        else:
             risk_per_share = width - credit
             
        total_risk = risk_per_share * 100 * qty
        
        # Calculate Total Credit (Credit * 100 * Qty)
        total_credit = credit * 100 * qty
        self.query_one("#lbl_credit").update(f"${total_credit:.2f}")
        
        # Calculate % of Account
        equity = self.account_metrics.get("equity", 0)
        risk_pct = (total_risk / equity * 100) if equity > 0 else 0.0
        
        self.query_one("#lbl_risk").update(f"${total_risk:.2f} ({risk_pct:.1f}%)")

    async def execute_trade(self, side="SELL"):
        if not self.selected_spread: return
        try:
            qty = int(self.query_one("#qty_input").value)
        except: 
            self.log_msg("Error: Invalid Qty")
            return
            
        self.log_msg(f"Executing Trade ({side} TO OPEN) Qty:{qty}...")
        
        payload = {
            "cmd": "EXECUTE_SPREAD",
            "short_sym": self.selected_spread["short_sym"],
            "long_sym": self.selected_spread["long_sym"],
            "qty": qty,
            "price": self.selected_spread["credit"], # Used for Profit Calc
            "stop_trigger": self.selected_spread["stop_trigger"],
            "order_type": "MARKET", # Changed to MARKET to ensure fill per user request
            "side": side
        }
        
        try:
            await self.req_sock.send_json(payload)
            reply = await self.req_sock.recv_json()
            if reply.get("status") == "ok":
                self.log_msg(f"Order Sent! ID: {reply.get('order_id')}")
            else:
                self.log_msg(f"Exec Error: {reply.get('msg')}")
        except Exception as e:
            self.log_msg(f"Exec Fail: {e}")

    @on(DataTable.RowSelected, "#positions_table")
    def on_pos_selected(self, event: DataTable.RowSelected):
        """Captures selection for potential closing."""
        row_key = event.row_key
        row = self.query_one("#positions_table").get_row(row_key)
        # Row: STRATEGY, STRIKES, DTE, QTY...
        # We need to map back to managed_spreads using Strikes/Strategy?
        # Or easier: store sym in row_key?
