import subprocess
import json

# Sui Smart Contract Constants (Testnet)
PACKAGE_ID = "0x08ecb6ca2664cb2ec5aeda6fb1ef87ed142becc206fc9c735cdfe2674828a615"
REGISTRY_ID = "0x7b1d0dd383c8e02391fb15a7fe116f6095a391fa99392f277cf09f29b4665cb8"
SUI_RPC_URL = "https://fullnode.testnet.sui.io:443"

def is_authorized(video_id: str, user_address: str) -> bool:
    """
    Check if a user is authorized for a video ID on-chain.
    Uses an HTTP JSON-RPC call to sui_devInspectTransactionBlock.
    """
    try:
        # Build the Move call transaction block payload for dev-inspect
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sui_devInspectTransactionBlock",
            "params": [
                user_address, # sender
                {
                    "kind": "ProgrammableTransaction",
                    "inputs": [
                        { "type": "pure", "valueType": "string", "value": video_id },
                        { "type": "object", "objectId": REGISTRY_ID }
                    ],
                    "transactions": [
                        {
                            "MoveCall": {
                                "package": PACKAGE_ID,
                                "module": "video_registry",
                                "function": "is_authorized",
                                "arguments": [
                                    {"Input": 1}, # REGISTRY_ID
                                    {"Input": 0}, # video_id string
                                    {"Input": 0}  # using user_address (represented as a string pure implicitly here, but really needs to be an address. Let's send the address as a pure argument)
                                ]
                            }
                        }
                    ]
                },
                None, # gasPrice
                None  # epoch
            ]
        }
        
        # Actually, reconstructing the raw PTB json is complex. 
        # A far more robust way in Python without a heavy SDK is just using the CLI but explicitly setting the env/url.
        # But wait! I can just use the exact CLI command but pass --rpc "https://fullnode.testnet.sui.io:443" to ensure it hits the right network!
        
        cmd = [
            "sui", "client", "call",
            "--package", PACKAGE_ID,
            "--module", "video_registry",
            "--function", "is_authorized",
            "--args", REGISTRY_ID, f"string:{video_id}", user_address,
            "--dev-inspect",
            "--json" # this is important
        ]
        
        print(f"[SUI] Executing: {' '.join(cmd)}")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        
        if proc.returncode != 0:
            print(f"[SUI ERROR] CLI failed: {proc.stderr}")
            return False
            
        result = json.loads(proc.stdout)
        
        results = result.get("results", [])
        if not results:
            print("[SUI ERROR] No results in JSON response")
            return False
            
        return_values = results[0].get("returnValues", [])
        if not return_values:
            print("[SUI ERROR] No returnValues in JSON response")
            return False
            
        val_bytes = return_values[0][0]
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
