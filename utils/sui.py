import os
import json
import urllib.request
import urllib.error
from utils.logger import logger

# On-chain object IDs — set these after deploying the smart contracts
PACKAGE_ID  = os.environ.get("SUI_PACKAGE_ID",  "0x0")
REGISTRY_ID = os.environ.get("SUI_REGISTRY_ID", "0x0")
ACCESS_STORE_ID = os.environ.get("SUI_ACCESS_STORE_ID", "0x0")

# The Node.js sui-auth-proxy handles devInspectTransactionBlock calls
SUI_AUTH_PROXY_URL = os.environ.get("SUI_AUTH_PROXY_URL", "http://127.0.0.1:8002")


def is_authorized(video_id: str, user_address: str) -> bool:
    """
    Check on-chain whether `user_address` has access to `video_id`.

    Routes through the sui-auth-proxy (Node.js) which calls
    devInspectTransactionBlock against the Sui fullnode.

    Returns False (deny access) on any error so auth failures are safe-default.
    """
    if PACKAGE_ID == "0x0" or REGISTRY_ID == "0x0":
        logger.warning(
            "SUI_PACKAGE_ID / SUI_REGISTRY_ID not configured — skipping on-chain auth check. "
            "Set these env vars after deploying the smart contracts."
        )
        return False

    url = (
        f"{SUI_AUTH_PROXY_URL}/check"
        f"?video_id={urllib.parse.quote(video_id)}"
        f"&user_address={urllib.parse.quote(user_address)}"
    )

    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "WalrusControlPlane/1.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            authorized = bool(body.get("authorized", False))
            logger.info(
                "On-chain auth result: %s",
                authorized,
                extra={"video_id": video_id, "user_address": user_address},
            )
            return authorized

    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        logger.error(
            "sui-auth-proxy returned HTTP %d: %s",
            e.code,
            err_body,
            extra={"video_id": video_id, "user_address": user_address},
        )
        return False

    except Exception as e:
        logger.error(
            "Failed to reach sui-auth-proxy: %s",
            e,
            extra={"video_id": video_id, "user_address": user_address},
        )
        return False


# Needed for urllib.parse in the function above
import urllib.parse
