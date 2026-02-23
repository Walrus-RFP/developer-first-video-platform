const express = require('express');
const cors = require('cors');
const { SuiClient, getFullnodeUrl } = require('@mysten/sui/client');
const { Transaction } = require('@mysten/sui/transactions');

const app = express();
app.use(cors());
app.use(express.json());

const PACKAGE_ID = "0x08ecb6ca2664cb2ec5aeda6fb1ef87ed142becc206fc9c735cdfe2674828a615";
const REGISTRY_ID = "0x7b1d0dd383c8e02391fb15a7fe116f6095a391fa99392f277cf09f29b4665cb8";
const client = new SuiClient({ url: getFullnodeUrl('testnet') });

app.get('/check', async (req, res) => {
    try {
        const { video_id, user_address } = req.query;
        if (!video_id || !user_address) {
            return res.status(400).json({ error: "Missing video_id or user_address" });
        }

        const tx = new Transaction();
        tx.moveCall({
            target: `${PACKAGE_ID}::video_registry::is_authorized`,
            arguments: [
                tx.object(REGISTRY_ID),
                tx.pure.string(video_id),
                tx.pure.address(user_address)
            ]
        });

        const result = await client.devInspectTransactionBlock({
            transactionBlock: tx,
            sender: user_address,
        });

        if (result.error) {
            console.error("Inspector Error:", result.error);
            return res.status(500).json({ error: result.error, authorized: false });
        }

        const returnValues = result.results?.[0]?.returnValues;
        if (!returnValues || returnValues.length === 0) {
            return res.json({ authorized: false, reason: "No return values" });
        }

        // valBytes[0][0] is a byte array where [1] is true, [0] is false
        const valBytes = returnValues[0][0];
        const isAuthorized = valBytes[0] === 1;

        return res.json({ authorized: isAuthorized });
    } catch (error) {
        console.error("Error evaluating Sui Tx:", error);
        return res.status(500).json({ error: error.message, authorized: false });
    }
});

const port = process.env.PORT || 8002;
app.listen(port, () => {
    console.log(`Sui Auth Proxy running on port ${port}`);
});
