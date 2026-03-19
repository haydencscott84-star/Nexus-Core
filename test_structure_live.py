import structure_nexus
import json
import os
import time

def test_live_structure():
    print("🧪 STARTING LIVE TEST: Structure Nexus Logic...")
    
    # Run one cycle
    try:
        structure_nexus.run_structure_cycle()
        
        # Check output file
        output_file = structure_nexus.OUTPUT_FILE
        if os.path.exists(output_file):
            print(f"✅ Output file found: {output_file}")
            with open(output_file, 'r') as f:
                data = json.load(f)
                
            print("-" * 50)
            print("📊 GENERATED STRUCTURE DATA:")
            print(json.dumps(data, indent=2))
            print("-" * 50)
            
            # Verify new fields
            metrics = data.get("trend_metrics", {})
            if "stack_status" in metrics and "extension_from_20sma" in metrics:
                print("✅ SUCCESS: New Trend Logic fields present.")
                print(f"   -> Stack: {metrics['stack_status']}")
                print(f"   -> Extension: {metrics['extension_from_20sma']}% ({metrics['extension_status']})")
            else:
                print("❌ FAILURE: New fields missing from output.")
                
        else:
            print("❌ FAILURE: Output file not created.")
            
    except Exception as e:
        print(f"❌ EXCEPTION during test: {e}")

if __name__ == "__main__":
    test_live_structure()
