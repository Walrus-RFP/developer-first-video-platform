import subprocess
import json
from utils.logger import logger

# Sui Smart Contract Constants (Testnet)
PACKAGE_ID = "0x08ecb6ca2664cb2ec5aeda6fb1ef87ed142becc206fc9c735cdfe2674828a615"
REGISTRY_ID = "0x7b1d0dd383c8e02391fb15a7fe116f6095a391fa99392f277cf09f29b4665cb8"
SUI_RPC_URL = "https://fullnode.testnet.sui.io:443"

def is_authorized(video_id: str, user_address: str) -> bool:
    """
    Check if a user is authorized for a video ID on-chain using the pysui SDK.
    """
    try:
        from pysui import SuiConfig, SyncClient
        from pysui.sui.sui_txn import SyncTransaction
    except ImportError:
        logger.error("pysui is not installed. Run: pip install pysui")
        return False
        
    try:
        # Create a config targeting Testnet natively
        cfg = SuiConfig.user_config(rpc_url="https://fullnode.testnet.sui.io:443")
        client = SyncClient(cfg)
        
        # Build the Programmable Transaction
        tx = SyncTransaction(client, initial_sender=user_address)
        
        # The arguments must be provided exactly as the contract expects them:
        # fun is_authorized(registry: &Registry, video_id: String, user: address): bool
        target = f"{PACKAGE_ID}::video_registry::is_authorized"
        
        # We need to pass the Object ID for the Registry
        registry_obj = tx.split_arg(REGISTRY_ID)
        video_id_arg = tx.split_arg(video_id)
        user_arg = tx.split_arg(user_address)
        
        tx.move_call(
            target=target,
            arguments=[registry_obj, video_id_arg, user_arg]
        )
        
        # Dry-run the transaction block to inspect the return value
        result = tx.inspect_all()
        
        if result.is_ok():
            inspect_result = result.result_data
            if hasattr(inspect_result, "results") and inspect_result.results:
                return_values = inspect_result.results[0].return_values
                if return_values and len(return_values) > 0:
                    # 'val_bytes' will be a list of bytes like [1] for true, [0] for false
                    val_bytes = return_values[0][0]
                    return val_bytes == [1]
                    
        logger.error("Inspection failed or no results. Detail: %s", result.result_string)
        return False
        
    except Exception as e:
        logger.error("Permission check failed: %s", e)
        return False

if __name__ == "__main__":
    test_video = "test_video_123"
    test_user = "0x1ebda9acfd4a9c4cd9615b18e59315b048e6e876a0fafdbf251a960215f6727f"
    logger.info("Checking auth for %s on %s", test_user, test_video)
    auth = is_authorized(test_video, test_user)
    logger.info("Authorized: %s", auth)
