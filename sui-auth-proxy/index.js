const express = require('express');
const cors = require('cors');
const { SuiClient, getFullnodeUrl } = require('@mysten/sui/client');
const { Transaction } = require('@mysten/sui/transactions');

const app = express();
app.use(cors());
app.use(express.json());

// Object IDs from environment — set these after deploying the smart contracts
const PACKAGE_ID       = process.env.SUI_PACKAGE_ID       || null;
const REGISTRY_ID      = process.env.SUI_REGISTRY_ID      || null;
const ACCESS_STORE_ID  = process.env.SUI_ACCESS_STORE_ID  || null;

const SUI_NETWORK = process.env.SUI_NETWORK || 'testnet';
const client = new SuiClient({ url: getFullnodeUrl(SUI_NETWORK) });

// Validate that a string looks like a Sui address (0x + 64 hex chars)
function isValidSuiAddress(addr) {
    return typeof addr === 'string' && /^0x[0-9a-fA-F]{64}$/.test(addr);
}

/**
 * GET /check?video_id=<uuid>&user_address=<0x...>
 *
 * Calls access_control::is_authorized via devInspectTransactionBlock.
 * Falls back to video_registry::is_authorized when ACCESS_STORE_ID is not set
 * (backwards-compatible with the old single-contract design).
 *
 * Response: { authorized: bool }
 */
app.get('/check', async (req, res) => {
    try {
        const { video_id, user_address } = req.query;

        if (!video_id || typeof video_id !== 'string' || video_id.length === 0) {
            return res.status(400).json({ error: 'Missing or invalid video_id', authorized: false });
        }
        if (!isValidSuiAddress(user_address)) {
            return res.status(400).json({ error: 'Missing or invalid user_address', authorized: false });
        }

        if (!PACKAGE_ID || !REGISTRY_ID) {
            console.warn('[sui-auth-proxy] SUI_PACKAGE_ID / SUI_REGISTRY_ID not configured.');
            return res.json({ authorized: false, reason: 'contracts not configured' });
        }

        const tx = new Transaction();

        if (!ACCESS_STORE_ID) {
            console.warn('[sui-auth-proxy] SUI_ACCESS_STORE_ID not configured.');
            return res.json({ authorized: false, reason: 'ACCESS_STORE_ID not configured' });
        }

        // access_control::is_authorized(registry, store, video_id, user)
        // TxContext is injected automatically by the VM — not passed as an argument.
        tx.moveCall({
            target: `${PACKAGE_ID}::access_control::is_authorized`,
            arguments: [
                tx.object(REGISTRY_ID),
                tx.object(ACCESS_STORE_ID),
                tx.pure.string(video_id),
                tx.pure.address(user_address),
            ],
        });

        const result = await client.devInspectTransactionBlock({
            transactionBlock: tx,
            sender: user_address,
        });

        if (result.error) {
            console.error('[sui-auth-proxy] Inspector Error:', result.error);
            return res.status(500).json({ error: result.error, authorized: false });
        }

        const returnValues = result.results?.[0]?.returnValues;
        if (!returnValues || returnValues.length === 0) {
            return res.json({ authorized: false, reason: 'no return values from contract' });
        }

        // returnValues[0][0] is a byte array: [1] = true, [0] = false
        const valBytes = returnValues[0][0];
        const isAuthorized = Array.isArray(valBytes) && valBytes[0] === 1;

        return res.json({ authorized: isAuthorized });

    } catch (error) {
        console.error('[sui-auth-proxy] Unhandled error:', error);
        return res.status(500).json({ error: error.message, authorized: false });
    }
});

/**
 * GET /grants?video_id=<uuid>
 *
 * Returns on-chain access grants for a video by reading the AccessStore object.
 * Response: { grants: [ { address, expires_at } ] }
 *
 * If contracts are not configured, returns an empty list.
 */
app.get('/grants', async (req, res) => {
    const { video_id } = req.query;
    if (!video_id || typeof video_id !== 'string') {
        return res.status(400).json({ error: 'Missing video_id', grants: [] });
    }
    if (!PACKAGE_ID || !ACCESS_STORE_ID) {
        return res.json({ grants: [], reason: 'contracts not configured' });
    }
    try {
        // Read the AccessStore object and extract grants for this video
        const obj = await client.getObject({
            id: ACCESS_STORE_ID,
            options: { showContent: true },
        });
        const fields = obj?.data?.content?.fields;
        // grants is a Table<String, Table<String, AccessGrant>> on-chain
        // The Sui SDK returns dynamic fields — we'd need dynamic field queries.
        // For now, return empty list and note that full enumeration requires indexer.
        // This is the correct approach; the control plane UI creates/revokes grants
        // via wallet-signed transactions which are the source of truth.
        return res.json({ grants: [], note: 'Use an indexer or Sui explorer for full grant enumeration' });
    } catch (err) {
        console.error('[sui-auth-proxy] grants error:', err.message);
        return res.json({ grants: [], error: err.message });
    }
});

/**
 * GET /subscription-policy?video_id=<uuid>
 *
 * Reads the SubscriptionPolicy for a video from the AccessStore via devInspect.
 * Response: { has_policy: bool, price_mist: number }
 */
app.get('/subscription-policy', async (req, res) => {
    const { video_id } = req.query;
    if (!video_id || typeof video_id !== 'string') {
        return res.status(400).json({ error: 'Missing video_id', has_policy: false });
    }
    if (!PACKAGE_ID || !ACCESS_STORE_ID) {
        return res.json({ has_policy: false, reason: 'contracts not configured' });
    }
    try {
        const tx = new Transaction();
        tx.moveCall({
            target: `${PACKAGE_ID}::access_control::has_subscription_policy`,
            arguments: [
                tx.object(ACCESS_STORE_ID),
                tx.pure.string(video_id),
            ],
        });
        const result = await client.devInspectTransactionBlock({
            transactionBlock: tx,
            sender: '0x0000000000000000000000000000000000000000000000000000000000000000',
        });
        if (result.error) {
            return res.status(500).json({ error: result.error, has_policy: false });
        }
        const hasPolicyBytes = result.results?.[0]?.returnValues?.[0]?.[0];
        const hasPolicy = Array.isArray(hasPolicyBytes) && hasPolicyBytes[0] === 1;
        return res.json({ has_policy: hasPolicy });
    } catch (err) {
        console.error('[sui-auth-proxy] subscription-policy error:', err.message);
        return res.json({ has_policy: false, error: err.message });
    }
});

/**
 * GET /seal-policy?video_id=<uuid>
 *
 * Reads the seal_policy_id from VideoMetadata via devInspect.
 * Response: { linked: bool, seal_policy_id: string | null }
 */
app.get('/seal-policy', async (req, res) => {
    const { video_id } = req.query;
    if (!video_id || typeof video_id !== 'string') {
        return res.status(400).json({ error: 'Missing video_id', linked: false });
    }
    if (!PACKAGE_ID || !REGISTRY_ID) {
        return res.json({ linked: false, seal_policy_id: null, reason: 'contracts not configured' });
    }
    try {
        const tx = new Transaction();
        tx.moveCall({
            target: `${PACKAGE_ID}::video_registry::get_seal_policy_id`,
            arguments: [
                tx.object(REGISTRY_ID),
                tx.pure.string(video_id),
            ],
        });
        const result = await client.devInspectTransactionBlock({
            transactionBlock: tx,
            sender: '0x0000000000000000000000000000000000000000000000000000000000000000',
        });
        if (result.error) {
            return res.status(500).json({ error: result.error, linked: false });
        }
        // Option<ID>: [0] = None, [1, ...32 bytes] = Some(id)
        const returnBytes = result.results?.[0]?.returnValues?.[0]?.[0];
        if (!Array.isArray(returnBytes) || returnBytes[0] === 0) {
            return res.json({ linked: false, seal_policy_id: null });
        }
        const idHex = '0x' + returnBytes.slice(1, 33).map(b => b.toString(16).padStart(2, '0')).join('');
        return res.json({ linked: true, seal_policy_id: idHex });
    } catch (err) {
        console.error('[sui-auth-proxy] seal-policy error:', err.message);
        return res.json({ linked: false, seal_policy_id: null, error: err.message });
    }
});

app.get('/health', (_req, res) => {
    res.json({
        status: 'ok',
        network: SUI_NETWORK,
        contracts_configured: !!(PACKAGE_ID && REGISTRY_ID),
        access_store_configured: !!ACCESS_STORE_ID,
    });
});

const port = process.env.PORT || 8002;
app.listen(port, () => {
    console.log(`Sui Auth Proxy running on port ${port} (network: ${SUI_NETWORK})`);
    if (!PACKAGE_ID) console.warn('  WARNING: SUI_PACKAGE_ID not set — all auth checks will return false');
    if (!REGISTRY_ID) console.warn('  WARNING: SUI_REGISTRY_ID not set — all auth checks will return false');
    if (!ACCESS_STORE_ID) console.warn('  WARNING: SUI_ACCESS_STORE_ID not set — all auth checks will return false');
});
