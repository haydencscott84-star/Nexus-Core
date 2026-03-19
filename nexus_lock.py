import sys
import os
import fcntl
import atexit

def enforce_singleton(script_name=None):
    """
    Enforces that only one instance of the script is running using a file lock.
    If the lock cannot be acquired, the script prints an error and exits.
    
    Args:
        script_name (str, optional): The name of the script. If None, uses sys.argv[0].
    """
    if script_name is None:
        script_name = sys.argv[0]
        
    base_name = os.path.basename(script_name)
    # Handle cases where script might be run as "python script.py" or "./script.py"
    clean_name = base_name.replace(".py", "")
    
    lock_file_path = f"/tmp/{clean_name}.lock"
    
    try:
        # Open the lock file (create if not exists)
        # We keep the file handle open globally to maintain the lock
        global _lock_file_handle
        _lock_file_handle = open(lock_file_path, 'w')
        
        # Try to acquire an exclusive lock (non-blocking)
        fcntl.lockf(_lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        
        # If we got here, we have the lock
        # print(f"[LOCK] Acquired lock for {clean_name}")
        
        # Register cleanup
        def cleanup():
            try:
                # fcntl locks are released on close/exit, but we can try to remove the file
                # Removing the file is actually risky if another process is racing to create it,
                # but for simple singleton enforcement it keeps /tmp clean.
                # However, standard practice for pidfiles/lockfiles is often to leave them.
                # Let's just close the handle.
                if _lock_file_handle:
                    _lock_file_handle.close()
                # os.remove(lock_file_path) # Optional: Remove file
            except: pass
            
        atexit.register(cleanup)
        
    except IOError:
        # Lock is held by another process
        print(f"⛔ [LOCK ERROR] {clean_name} is already running. Aborting.")
        sys.exit(1) # CHANGED to 1 to signal error to Launcher
    except Exception as e:
        print(f"⛔ [LOCK ERROR] Could not acquire lock for {clean_name}: {e}")
        sys.exit(1)
