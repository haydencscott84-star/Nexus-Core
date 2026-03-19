import os
import sqlite3
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv

# ==========================================
# Configuration & Setup
# ==========================================
DB_FILE = "spy_options_history.db"
LOG_FILE = "spy_oi_fetch.log"
TARGET_TICKER = "SPY"
ORATS_EOD_URL = "https://api.orats.io/datav2/strikes" 

# Configure logging (Output to both File and Console)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

# Load Environment Variables from .env file
load_dotenv()
ORATS_API_KEY = os.getenv("ORATS_API_KEY")


# ==========================================
# Database Architecture
# ==========================================
def setup_database():
    """Initializes the SQLite database and creates the spy_oi_history table."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Build schema with composite primary key to prevent duplicate entries
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS spy_oi_history (
                trade_date DATE,
                expiration_date DATE,
                strike DECIMAL,
                option_type VARCHAR(4),
                volume INT,
                open_interest INT,
                PRIMARY KEY (trade_date, expiration_date, strike, option_type)
            )
        ''')
        conn.commit()
        logging.info("Database architecture verified successfully.")
        return conn
    except sqlite3.Error as e:
        logging.error(f"Failed to initialize database: {e}")
        return None


# ==========================================
# API Integration & Filtering
# ==========================================
def fetch_orats_eod_data(trade_date_str: str):
    """Fetches EOD options data from ORATS API for the specified trade date."""
    if not ORATS_API_KEY:
        logging.error("CRITICAL: ORATS_API_KEY not found in .env file.")
        return None
        
    params = {
        'token': ORATS_API_KEY,
        'ticker': TARGET_TICKER,
        'tradeDate': trade_date_str
    }
    
    try:
        logging.info(f"Querying ORATS API for {TARGET_TICKER} on trade date: {trade_date_str}...")
        response = requests.get(ORATS_EOD_URL, params=params, timeout=30)
        response.raise_for_status()
        
        payload = response.json()
        return payload.get('data', [])
        
    except requests.exceptions.RequestException as e:
        logging.error(f"HTTP Request failed during ORATS data pull: {e}")
        return None
    except ValueError as e:
        logging.error(f"Failed to parse JSON response from ORATS: {e}")
        return None

def process_and_store_data(conn, data, trade_date: str):
    """
    Parses JSON payload, filters exclusively for Friday expirations, 
    and inserts records into the SQLite database.
    """
    if not data:
        logging.warning("No data payload received to process.")
        return

    cursor = conn.cursor()
    records_to_insert = []
    
    for item in data:
        exp_date_str = item.get('expirDate')
        if not exp_date_str:
            continue
            
        try:
            exp_date = datetime.strptime(exp_date_str, "%Y-%m-%d").date()
            
            # Constraint: Filter so ONLY Friday expirations are processed (Monday=0, Friday=4)
            if exp_date.weekday() != 4:
                continue
                
            strike = float(item.get('strike', 0.0))
            
            # Extract Call Metrics
            c_vol = int(item.get('callVolume', 0))
            c_oi = int(item.get('callOpenInterest', 0))
            records_to_insert.append((trade_date, exp_date_str, strike, 'Call', c_vol, c_oi))
            
            # Extract Put Metrics
            p_vol = int(item.get('putVolume', 0))
            p_oi = int(item.get('putOpenInterest', 0))
            records_to_insert.append((trade_date, exp_date_str, strike, 'Put', p_vol, p_oi))
            
        except ValueError as e:
            logging.warning(f"Data conversion error on row: {e} | Payload: {item}")
            continue

    if records_to_insert:
        try:
            # INSERT OR REPLACE ensures idempotency if the cron job runs twice on the same day
            cursor.executemany('''
                INSERT OR REPLACE INTO spy_oi_history 
                (trade_date, expiration_date, strike, option_type, volume, open_interest)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', records_to_insert)
            conn.commit()
            logging.info(f"Successfully processed and committed {len(records_to_insert)} Friday expiration records to database.")
        except sqlite3.Error as e:
            logging.error(f"Database insertion transaction failed: {e}")
            conn.rollback()
    else:
        logging.info("No records matched the Friday expiration constraint during this run.")


# ==========================================
# Analytical Helper Query
# ==========================================
def calculate_delta_oi(conn, target_expiration: str):
    """
    Helper function executing a SQL query to calculate the day-over-day
    Change in Open Interest (Δ OI) for the highest volume strikes 
    for a specific Friday expiration date.
    """
    query = '''
    WITH distinct_dates AS (
        SELECT DISTINCT trade_date FROM spy_oi_history ORDER BY trade_date DESC LIMIT 2
    ),
    latest_date AS (
        SELECT trade_date FROM distinct_dates LIMIT 1 OFFSET 0
    ),
    previous_date AS (
        SELECT trade_date FROM distinct_dates LIMIT 1 OFFSET 1
    ),
    latest_oi AS (
        SELECT strike, option_type, volume, open_interest as latest_oi
        FROM spy_oi_history
        WHERE trade_date = (SELECT trade_date FROM latest_date)
          AND expiration_date = ?
    ),
    prev_oi AS (
        SELECT strike, option_type, open_interest as prev_oi
        FROM spy_oi_history
        WHERE trade_date = (SELECT trade_date FROM previous_date)
          AND expiration_date = ?
    )
    SELECT 
        l.strike, 
        l.option_type, 
        l.latest_oi, 
        COALESCE(p.prev_oi, 0) as prev_oi,
        (l.latest_oi - COALESCE(p.prev_oi, 0)) as delta_oi,
        l.volume
    FROM latest_oi l
    LEFT JOIN prev_oi p ON l.strike = p.strike AND l.option_type = p.option_type
    ORDER BY l.volume DESC
    LIMIT 20;
    '''
    try:
        cursor = conn.cursor()
        cursor.execute(query, (target_expiration, target_expiration))
        results = cursor.fetchall()
        
        logging.info(f"Calculated Δ OI for expiration: {target_expiration}")
        
        print(f"\n--- Day-over-Day Δ Open Interest Report: {target_expiration} ---")
        print(f"{'Strike':<8} | {'Type':<6} | {'Latest OI':<10} | {'Prev OI':<10} | {'Δ OI':<8} | {'Volume':<10}")
        print("-" * 65)
        for row in results:
            strike, opt_type, latest_oi, prev_oi, delta_oi, vol = row
            print(f"{strike:<8.1f} | {opt_type:<6} | {latest_oi:<10} | {prev_oi:<10} | {delta_oi:<8+} | {vol:<10}")
        print("-" * 65)
        
        return results
    except sqlite3.Error as e:
        logging.error(f"Failed to calculate Delta OI due to database error: {e}")
        return None


# ==========================================
# Daily Execution Logic (Cron Gateway)
# ==========================================
def main():
    """
    Main execution pipeline designed to be triggered by a Cron schedule
    (e.g., 30 16 * * 1-5 python3 /path/to/fetch_spy_oi_history.py)
    """
    logging.info("=== Initializing Daily SPY EOD Open Interest Pipeline ===")
    
    conn = setup_database()
    if not conn:
        return
        
    # Standardize trade_date assignment (e.g. '2026-03-12')
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Access API Layer
    orats_payload = fetch_orats_eod_data(today_str)
    
    # 2. Extract, Transform, Load (ETL)
    if orats_payload:
        process_and_store_data(conn, orats_payload, today_str)
        
        # [Optional] Run the helper function automatically to print the top 20 active volume strikes
        # calculate_delta_oi(conn, "2026-03-20") 
    else:
        logging.error("ETL Pipeline aborted due to missing API payload.")
        
    if conn:
        conn.close()
        logging.info("=== Pipeline Execution Complete. Database standard disconnect. ===")


if __name__ == "__main__":
    main()
