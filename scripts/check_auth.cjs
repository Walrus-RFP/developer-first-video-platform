const { SuiClient, getFullnodeUrl } = require('@mysten/sui/client');
const { Transaction } = require('@mysten/sui/transactions');

async function main() {
    const args = process.argv.slice(2);
    if (args.length < 2) {
        console.error("Usage: node check_auth.cjs <video_id> <user_address>");
        process.exit(1);
    }
    const [videoId, userAddress] = args;

    const PACKAGE_ID = "0x08ecb6ca2664cb2ec5aeda6fb1ef87ed142becc206fc9c735cdfe2674828a615";
    const REGISTRY_ID = "0x7b1d0dd383c8e02391fb15a7fe116f6095a391fa99392f277cf09f29b4665cb8";

    const client = new SuiClient({ url: getFullnodeUrl('testnet') });
    const tx = new Transaction();

    tx.moveCall({
        target: `${PACKAGE_ID}::video_registry::is_authorized`,
        arguments: [
            tx.object(REGISTRY_ID),
            tx.pure.string(videoId),
            tx.pure.address(userAddress)
        ]
    });

    try {
        const result = await client.devInspectTransactionBlock({
            transactionBlock: tx,
            sender: userAddress,
        });

        if (result.error) {
            console.error("Inspector Error:", result.error);
            process.exit(1);
        }

        const returnValues = result.results?.[0]?.returnValues;
        if (!returnValues || returnValues.length === 0) {
            console.error("No return values");
            process.exit(1);
        }

        const valBytes = returnValues[0][0]; // BCS bytes array
        if (valBytes[0] === 1) {
            console.log("true");
        } else {
            console.log("false");
        }
    } catch (e) {
        console.error(e);
        process.exit(1);
    }
}

main();
