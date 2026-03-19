
# FINAL PATCH PHASE 9: STABILITY & LOGIC
# Targets: nexus_debit_downloaded.py, nexus_spreads_downloaded.py

DEBIT_FILE = "nexus_debit_downloaded.py"
SPREADS_FILE = "nexus_spreads_downloaded.py"

# --- 1. DEBIT: Transient Panic Close ---
# Replaces panic_close_spread to avoid ZMQ contention
DEBIT_PANIC = r'''
    async def panic_close_spread(self, spread_data, reason="MANUAL"):
        """Sends immediate Close order using TRANSIENT socket to avoid contention."""
        self.log_msg(f"CLOSING SPREAD ({reason})...")
        
        # Transient ZMQ to prevent blocking main req_sock
        import zmq.asyncio
        ctx = zmq.asyncio.Context()
        sock = ctx.socket(zmq.REQ)
        sock.connect("tcp://127.0.0.1:5555")
        sock.setsockopt(zmq.RCVTIMEO, 2000) # 2s timeout
        
        payload = {
            "cmd": "CLOSE_SPREAD",
            "side": "SELL",
            "short_sym": spread_data["short_sym"],
            "long_sym": spread_data["long_sym"],
            "qty": 1
        }
        
        try:
            await sock.send_json(payload)
            reply = await sock.recv_json()
            self.log_msg(f"Close Sent: {reply.get('msg')} ({reply.get('order_id')})")
        except Exception as e:
            self.log_msg(f"Panic Close Failed: {e}")
        finally:
            sock.close()
            ctx.term()
'''

# --- 2. SPREADS: Repair Manager + Transient Panic Close ---

# Corrected Manager Loop (Indentation Fixed)
SPREADS_MANAGER = r'''
    async def auto_manager_loop(self):
        """
        Active Manager for Credit Spreads (Phase 9)
        1. DEFENSE: 0.5 Point Constraint
        """
        while True:
            await asyncio.sleep(1)
            # Use safe copying keys to avoid runtime modification errors if dict changes
            if not self.managed_spreads: continue
            
            items = list(self.managed_spreads.items())
            for short_sym, spread in items:
                short_strike = spread.get("short_strike", 0)
                is_call = "C" in short_sym
                
                # Logic: 0.5 Point Constraint
                if is_call: 
                    # Bear Call: Stop if Price >= Short - 0.5
                    stop_level = short_strike - 0.5
                else:
                    # Bull Put: Stop if Price <= Short + 0.5
                    stop_level = short_strike + 0.5
                    
                if self.current_spy_price > 0:
                    triggered = False
                    if is_call and self.current_spy_price >= stop_level: triggered = True
                    if not is_call and self.current_spy_price <= stop_level: triggered = True
                    
                    if triggered:
                        warn_msg = f"ðŸ›‘ STOP TRIGGERED: SPY {self.current_spy_price:.2f} breached {stop_level:.2f}"
                        # Check redundancy to avoid log spam
                        if self.selected_spread != spread:
                            self.log_msg(warn_msg)
                        
                        # Set as selected and Panic Close
                        self.selected_spread = spread 
                        await self.panic_close()
                        await asyncio.sleep(5) # Pause to allow close to process
'''

# Cleaned Panic Close (Transient Socket + Removing Duplicates)
SPREADS_PANIC = r'''
    async def panic_close(self):
        if not self.selected_spread: return
        self.log_msg("PANIC CLOSE: Executing Market Exit via Transient Socket...")
        
        import zmq.asyncio
        ctx = zmq.asyncio.Context()
        sock = ctx.socket(zmq.REQ)
        sock.connect("tcp://127.0.0.1:5555")
        sock.setsockopt(zmq.RCVTIMEO, 2000)

        payload = {
            "cmd": "CLOSE_SPREAD",
            "short_sym": self.selected_spread["short_sym"],
            "long_sym": self.selected_spread["long_sym"],
            "qty": 1 # Default 1
        }
        
        try:
            await sock.send_json(payload)
            reply = await sock.recv_json()
            if reply.get("status") == "ok":
                self.log_msg(f"Close Sent! ID: {reply.get('order_id')}")
            else:
                self.log_msg(f"Close Error: {reply.get('msg')}")
        except Exception as e:
            self.log_msg(f"Transient Close Failed: {e}")
        finally:
            sock.close()
            ctx.term()

    # End
'''

def replace_block(file_path, start_me, end_me, content):
    try:
        with open(file_path, 'r') as f: data = f.read()
        if start_me in data:
            pre, post = data.split(start_me, 1)
            # Find closest end marker
            if end_me in post:
                body, remainder = post.split(end_me, 1)
                # Ensure we don't accidentally drop the end marker if it's needed, 
                # but our pattern appends it back manually usually.
                # Here we just put content and then end_me.
                # Check indentation of content. It starts with newline generally.
                final = pre + content.strip() + "\n\n    " + end_me + remainder
                with open(file_path, 'w') as f: f.write(final)
                print(f"Patched: {file_path}")
            else: print(f"End marker '{end_me}' not found in {file_path}")
        else: print(f"Start marker '{start_me}' not found in {file_path}")
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    # DEBIT: Panic Close
    # Target: async def panic_close_spread...
    # End: def log_msg...
    replace_block(DEBIT_FILE, "async def panic_close_spread(self, spread_data, reason=\"MANUAL\"):", "def log_msg(self, msg):", DEBIT_PANIC)

    # SPREADS: Auto Manager Loop (Repair)
    # Target: async def auto_manager_loop...
    # End: async def active_quote_loop... (NO SPACES)
    # NOTE: The file might have corrupted indentation "        async def...".
    # replace_block splits by `start_me`. If I use "async def auto_manager_loop(self):", 
    # and file has "    async def...", split works. pre includes indent.
    # Logic: final = pre + content.strip() + ...
    # content.strip() removes indent.
    # pre has indent.
    # Result: Indent + Code.
    # IF PRE HAS 8 SPACES (Corruption), result has 8 spaces.
    # I NEED TO DEDENT PRE IF IT IS WRONG.
    # How? Check pre[-4:]?
    # Simple fix: Verify pre ends with `    ` (4 spaces). If it ends with `        `, strip 4.
    
    # Custom fix logic for this script:
    with open(SPREADS_FILE, 'r') as f: s_data = f.read()
    
    # 1. Repair Manager Loop
    start_tag = "async def auto_manager_loop(self):"
    end_tag = "async def active_quote_loop(self):"
    
    if start_tag in s_data:
        pre, post = s_data.split(start_tag, 1)
        if end_tag in post:
            body, remainder = post.split(end_tag, 1)
            # Fix Pre Indentation
            if pre.endswith("        "):
                 pre = pre[:-4]
                 print("Corrected Indentation (8->4)")
            
            final_code = pre + SPREADS_MANAGER.strip() + "\n\n    " + end_tag + remainder
            with open(SPREADS_FILE, 'w') as f: f.write(final_code)
            print("Repaired Spreads Manager Loop")
        else: print("End tag not found for Manager Loop")
    else: print("Start tag not found for Manager Loop")

    # 2. Repair Panic Close (Cleanup duplicates)
    # Target: async def panic_close(self):
    # End: if __name__ == "__main__":
    
    # Reload file
    with open(SPREADS_FILE, 'r') as f: s_data = f.read()
    
    start_tag_panic = "async def panic_close(self):"
    end_tag_panic = 'if __name__ == "__main__":'
    
    if start_tag_panic in s_data and end_tag_panic in s_data:
        pre, post = s_data.split(start_tag_panic, 1)
        body, remainder = post.split(end_tag_panic, 1)
        
        # We replace EVERYTHING from panic_close START to __main__ with New Panic Close Code
        # This deletes duplicates/garbage in between.
        
        final_code = pre + SPREADS_PANIC.strip() + "\n\n" + end_tag_panic + remainder
        with open(SPREADS_FILE, 'w') as f: f.write(final_code)
        print("Replaced Panic Close (Clean)")
    else:
        print("Could not find panic_close block to clean")
