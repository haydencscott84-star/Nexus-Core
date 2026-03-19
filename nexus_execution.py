import asyncio
import math

class NexusExecution:
    """
    Handles advanced execution logic like Adaptive Limit Walking.
    """
    
    @staticmethod
    async def smart_limit_walker(client, submit_func, start_price, side, max_slippage=0.03, step_seconds=3):
        """
        Submits an order at 'start_price' (Mid) and walks it toward Natural.
        
        Args:
            client: TradeStationManager instance (for modify/cancel).
            submit_func: Async function(price) -> returns order_id (or None).
            start_price: Initial Mid Price (Float).
            side: "BUY" or "SELL" (Determines walk direction).
            max_slippage: Maximum price movement allowed.
            step_seconds: Wait time between bumps.
            
        Returns:
            order_id (str) if filled, None if timed out/cancelled.
        """
        print(f"🕵️ WALKING ORDER ({side}): Starting @ {start_price}")
        
        # 1. Start at Mid
        current_price = float(start_price)
        side = side.upper()
        
        # Calculate limit cap
        if side in ['SELL', 'SELLTOOPEN', 'SELLTOCLOSE']: # Credit/Short
            limit_cap = current_price - max_slippage
            step = -0.01
        else: # Debit/Long
            limit_cap = current_price + max_slippage
            step = 0.01
        
        print(f"   START: {current_price} | CAP: {limit_cap:.2f}")
        
        # Submit Initial Order via Callback
        try:
            order_id = await submit_func(current_price)
            if not order_id:
                print("❌ Execution Failed: Initial Order Returned No ID.")
                return None
        except Exception as e:
            print(f"❌ Execution Exception: {e}")
            return None
            
        print(f"   OID: {order_id} @ {current_price}")
        
        # 2. Walk the Limit
        for _ in range(1, 4): # Try 3 steps
            await asyncio.sleep(step_seconds)
            
            # Check Status
            try:
                status = await asyncio.to_thread(client.get_order_status, order_id)
            except: status = "UNKNOWN"
            
            if status in ['FILLED', 'FLL']:
                print("✅ FILL CONFIRMED.")
                return order_id
                
            # Calc New Price
            new_price = round(current_price + step, 2)
            
            # Check Cap
            if (step < 0 and new_price < limit_cap) or (step > 0 and new_price > limit_cap):
                 print("✋ Limit Cap Reached.")
                 break 
                    
            # Modify Order
            if new_price != current_price:
                print(f"👉 NUDGING: {current_price} -> {new_price}")
                await asyncio.to_thread(client.modify_order, order_id, new_price)
                current_price = new_price
        
        # Final Check
        await asyncio.sleep(step_seconds)
        try:
            status = await asyncio.to_thread(client.get_order_status, order_id)
        except: status = "UNKNOWN"
        
        if status not in ['FILLED', 'FLL']:
            print("❌ TIMEOUT: Slippage limit reached. Cancelling.")
            await asyncio.to_thread(client.cancel_order, order_id)
            return None
            
        return order_id
