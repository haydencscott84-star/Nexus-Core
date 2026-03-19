import os
import json
import asyncio
from supabase import create_client, Client
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

# Supabase Credentials
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

_supabase_client = None

def get_supabase_client() -> Client:
    """
    Initialize and return the Supabase client.
    Requires SUPABASE_URL and SUPABASE_KEY to be in the .env file.
    """
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
        
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[Supabase Bridge] Warning: Supabase credentials not found in .env file.")
        return None
        
    try:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        return _supabase_client
    except Exception as e:
        print(f"[Supabase Bridge] Error initializing Supabase client: {e}")
        return None

async def upload_json_to_supabase(table_name: str, data: dict, id_field: str = "id", id_value: str = "latest"):
    """
    Uploads or updates JSON data in a Supabase table without blocking the event loop.
    We assume the table has at least 'id' (or another pk) and 'data' (jsonb/json) columns.
    """
    client = get_supabase_client()
    if not client:
        return False
        
    try:
        record = {
            id_field: id_value,
            "data": data
        }
        
        # Execute the synchronous supabase call in a thread pool
        response = await asyncio.to_thread(
            client.table(table_name).upsert(record).execute
        )
        return True
    except Exception as e:
        print(f"[Supabase Bridge] Error uploading to Supabase table '{table_name}': {e}")
        return False

# For testing
if __name__ == "__main__":
    client = get_supabase_client()
    if client:
        print(f"[Supabase Bridge] Supabase client initialized successfully. Connected to: {SUPABASE_URL}")
    else:
        print("[Supabase Bridge] Failed to initialize Supabase client.")
