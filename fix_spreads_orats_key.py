import os

TARGET_FILE = "/root/nexus_spreads.py"

def fix_imports_and_key():
    try:
        with open(TARGET_FILE, 'r') as f:
            lines = f.readlines()
        
        new_lines = []
        inserted = False
        
        for line in lines:
            new_lines.append(line)
            # Insert after the last import block or specifically after 'import aiohttp'
            if "import aiohttp" in line and not inserted:
                new_lines.append("import os\n")
                new_lines.append('ORATS_API_KEY = os.getenv("ORATS_API_KEY", os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))\n')
                inserted = True
        
        with open(TARGET_FILE, 'w') as f:
            f.writelines(new_lines)
            print("Imports and Key Fixed.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_imports_and_key()
