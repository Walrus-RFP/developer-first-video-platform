import subprocess
import json
import os

# Sui Smart Contract Constants (Testnet)
PACKAGE_ID = "0x08ecb6ca2664cb2ec5aeda6fb1ef87ed142becc206fc9c735cdfe2674828a615"
REGISTRY_ID = "0x7b1d0dd383c8e02391fb15a7fe116f6095a391fa99392f277cf09f29b4665cb8"

def is_authorized(video_id: str, user_address: str) -> bool:
    """
    Check if a user is authorized for a video ID on-chain.
    Uses 'sui client dev-inspect' to perform a read-only call.
    """
    try:
        # Construct the command
        cmd = [
            "sui", "client", "call",
            "--package", PACKAGE_ID,
            "--module", "video_registry",
            "--function", "is_authorized",
            "--args", REGISTRY_ID, f"string:{video_id}", user_address,
            "--dev-inspect",
            "--json"
        ]
        
        # Execute and capture output
        proc = subprocess.run(cmd, capture_output=True, text=True)
        
        if proc.returncode != 0:
            print(f"[SUI ERROR] CLI failed: {proc.stderr}")
            return False
            
        result = json.loads(proc.stdout)
        
        # Parse the results from the dev-inspect output
        # Sui dev-inspect returns a complex JSON structure. 
        # We need to look into 'results' -> first item -> 'returnValues'
        results = result.get("results", [])
        if not results:
            return False
            
        return_values = results[0].get("returnValues", [])
        if not return_values:
            return False
            
        # The first return value is our boolean (bcs encoded)
        # For a bool, 01 is True, 00 is False (usually represented as [1] or [0] in the json)
        val_bytes = return_values[0][0] # [[1], "bool"] -> [1]
        return val_bytes == [1]

    except Exception as e:
        print(f"[SUI EXCEPTION] Permission check failed: {e}")
        return False

if __name__ == "__main__":
    # Test with a dummy address and the registry
    # Note: Replace with a real test once we have a video registered
    test_video = "test_video_123"
    test_user = "0x1ebda9acfd4a9c4cd9615b18e59315b048e6e876a0fafdbf251a960215f6727f"
    print(f"Checking auth for {test_user} on {test_video}...")
    auth = is_authorized(test_video, test_user)
    print(f"Authorized: {auth}")
