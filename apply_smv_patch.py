
import os

FILES = ["/root/nexus_spreads.py", "/root/nexus_debit.py"]

def patch_file(filepath):
    try:
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            return False

        with open(filepath, 'r') as f:
            content = f.read()

        # Target line to replace (generic enough to match both files if possible, or specific)
        # They both use a similar structure in poll_orats_greeks
        
        # Look for the IV line
        target = "v = float(i.get('impliedVolatility', i.get('iv', 0)))"
        replacement = "v = float(i.get('smvVol', i.get('impliedVolatility', i.get('iv', 0))))"
        
        if target in content:
            new_content = content.replace(target, replacement)
            with open(filepath, 'w') as f:
                f.write(new_content)
            print(f"Patched {filepath} successfully.")
            return True
        else:
            print(f"Target not found in {filepath}. Check if already patched.")
            # Fallback for minor formatting differences if any (simple substring check usually works)
            return False

    except Exception as e:
        print(f"Error patching {filepath}: {e}")
        return False

if __name__ == "__main__":
    for fp in FILES:
        patch_file(fp)
