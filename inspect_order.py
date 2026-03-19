import sys, json, os, requests
sys.path.append(os.getcwd())

try:
    from tradestation_explorer import TradeStationManager
    from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

def inspect(order_id):
    print(f"Initializing TS Manager for Account {TS_ACCOUNT_ID}...")
    ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
    token = ts.access_token
    
    # Try fetching ALL orders (including today's closed/rejected)
    print(f"Fetching ALL orders for account {TS_ACCOUNT_ID}...")
    url = f"https://api.tradestation.com/v3/brokerage/accounts/{TS_ACCOUNT_ID}/orders"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            orders = r.json().get("Orders", [])
            print(f"Found {len(orders)} orders.")
            
            target = next((o for o in orders if str(o.get("OrderID")) == str(order_id)), None)
            
            if target:
                print("\n--- TARGET ORDER FOUND ---")
                print(json.dumps(target, indent=2))
                
                # Check for rejection reason
                if target.get("Status") == "Rejected":
                    print(f"\n❌ REJECTION REASON: {target.get('RejectReason', 'Unknown')}")
                    print(f"Message: {target.get('Message', '')}")
            else:
                print(f"❌ Order {order_id} NOT FOUND in listing.")
        else:
            print(f"Error fetching orders: {r.status_code} {r.text}")
            
    except Exception as e:
        print(f"Request Exception: {e}")

if __name__ == "__main__":
    oid = sys.argv[1] if len(sys.argv) > 1 else "1227880699"
    inspect(oid)
