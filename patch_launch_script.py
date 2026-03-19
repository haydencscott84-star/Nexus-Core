
# PATCH LAUNCH SCRIPT
# Target: launch_cockpit.sh
# Objective: Launch nexus_debit.py in Window 18

FILE = "launch_cockpit.sh"

SEARCH = "tmux send-keys -t $SESSION:18 'echo \"Window 18 Reserved\"' C-m"
REPLACE = "tmux send-keys -t $SESSION:18 'python3 robust_wrapper.py python3 nexus_debit.py' C-m"

SEARCH_TITLE = "tmux new-window -t $SESSION -n 'RESERVED'"
REPLACE_TITLE = "tmux new-window -t $SESSION -n 'DEBIT_SNIPER'"

def patch():
    with open(FILE, 'r') as f: content = f.read()
    
    if SEARCH in content:
        content = content.replace(SEARCH, REPLACE)
        content = content.replace(SEARCH_TITLE, REPLACE_TITLE)
        with open(FILE, 'w') as f: f.write(content)
        print("Updated launch_cockpit.sh for Nexus Debit.")
    else:
        print("Could not find Reserved Window line.")

if __name__ == "__main__":
    patch()
