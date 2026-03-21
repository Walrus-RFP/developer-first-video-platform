/**
 * Mysten Seal integration for WalStream.
 *
 * Seal provides threshold key management: the AES-GCM encryption key
 * for private videos is Seal-encrypted by the owner and stored on Walrus.
 * Viewers request decryption key shares from Seal nodes, which verify
 * on-chain access (via seal_approve in access_control.move) before
 * distributing shares. Only users with a valid AccessGrant can decrypt.
 *
 * Required env vars:
 *   NEXT_PUBLIC_SUI_PACKAGE_ID
 *   NEXT_PUBLIC_SUI_REGISTRY_ID
 *   NEXT_PUBLIC_SUI_ACCESS_STORE_ID
 */
import { Transaction } from "@mysten/sui/transactions";
import { SealClient, SessionKey, type SealCompatibleClient } from "@mysten/seal";

const PACKAGE_ID = process.env.NEXT_PUBLIC_SUI_PACKAGE_ID ?? "";
const REGISTRY_ID = process.env.NEXT_PUBLIC_SUI_REGISTRY_ID ?? "";
const ACCESS_STORE_ID = process.env.NEXT_PUBLIC_SUI_ACCESS_STORE_ID ?? "";

/**
 * Mysten Labs independent key servers on Sui testnet.
 * Source: https://seal-docs.wal.app/UsingSeal
 * threshold=2 means both servers must respond (2-of-2).
 */
const TESTNET_SERVER_CONFIGS = [
    {
        objectId: "0x73d05d62c18d9374e3ea529e8e0ed6161da1a141a94d3f76ae3fe4e99356db75",
        weight: 1,
    },
    {
        objectId: "0xf5d14a81a982144ae441cd7d64b09027f116a468bd36e7eca494f750591623c8",
        weight: 1,
    },
];

function toHex(bytes: Uint8Array): string {
    return Array.from(bytes)
        .map(b => b.toString(16).padStart(2, "0"))
        .join("");
}

/**
 * The Seal identity for a video is the hex-encoded UTF-8 bytes of its video_id.
 * This must match what seal_approve receives as `id: vector<u8>` on-chain.
 */
function videoIdToSealId(videoId: string): string {
    return toHex(new TextEncoder().encode(videoId));
}

function createSealClient(suiClient: SealCompatibleClient): SealClient {
    return new SealClient({
        suiClient,
        serverConfigs: TESTNET_SERVER_CONFIGS,
        verifyKeyServers: false, // set true in production
    });
}

/**
 * Seal-encrypt an AES-GCM key for a video.
 * Called by the video owner immediately after upload.
 *
 * @param suiClient  — connected Sui RPC client
 * @param videoId    — the platform video UUID
 * @param aesKeyB64  — base64-encoded 32-byte AES key (from /encryption-key endpoint)
 * @returns          — raw encrypted object bytes, ready to upload to Walrus
 */
export async function sealEncryptVideoKey(
    suiClient: SealCompatibleClient,
    videoId: string,
    aesKeyB64: string,
): Promise<Uint8Array> {
    if (!PACKAGE_ID) throw new Error("NEXT_PUBLIC_SUI_PACKAGE_ID not configured");

    const client = createSealClient(suiClient);
    const aesKeyBytes = Uint8Array.from(atob(aesKeyB64), c => c.charCodeAt(0));

    const { encryptedObject } = await client.encrypt({
        threshold: 2,
        packageId: PACKAGE_ID,
        id: videoIdToSealId(videoId),
        data: aesKeyBytes,
    });

    return encryptedObject;
}

/**
 * Seal-decrypt a video's AES key.
 * Called by a viewer before playback of a private Seal-encrypted video.
 *
 * @param suiClient            — connected Sui RPC client
 * @param videoId              — the platform video UUID
 * @param encryptedKeyBytes    — raw bytes fetched from /v1/seal-blob/{blob_id}
 * @param walletAddress        — viewer's Sui address
 * @param signPersonalMessage  — wallet sign function (from useSignPersonalMessage)
 * @returns                    — base64-encoded AES key, ready to pass to /playback-url
 */
export async function sealDecryptVideoKey(
    suiClient: SealCompatibleClient,
    videoId: string,
    encryptedKeyBytes: Uint8Array,
    walletAddress: string,
    signPersonalMessage: (input: { message: Uint8Array }) => Promise<{ signature: string }>,
): Promise<string> {
    if (!PACKAGE_ID) throw new Error("NEXT_PUBLIC_SUI_PACKAGE_ID not configured");
    if (!REGISTRY_ID || !ACCESS_STORE_ID)
        throw new Error("SUI_REGISTRY_ID / SUI_ACCESS_STORE_ID not configured");

    const sealClient = createSealClient(suiClient);

    // 1. Create a short-lived session key (static factory, not constructor)
    const sessionKey = await SessionKey.create({
        address: walletAddress,
        packageId: PACKAGE_ID,
        ttlMin: 10,
        suiClient,
    });

    // 2. Sign the session key's personal message with the user's wallet
    const { signature } = await signPersonalMessage({
        message: sessionKey.getPersonalMessage(),
    });
    await sessionKey.setPersonalMessageSignature(signature);

    // 3. Build the transaction calling seal_approve on-chain.
    //    Seal nodes execute this via devInspect to verify the viewer's access.
    const idBytes = new TextEncoder().encode(videoId);
    const tx = new Transaction();
    tx.moveCall({
        target: `${PACKAGE_ID}::access_control::seal_approve`,
        arguments: [
            tx.pure.vector("u8", Array.from(idBytes)),
            tx.object(REGISTRY_ID),
            tx.object(ACCESS_STORE_ID),
        ],
    });
    const txBytes = await tx.build({ client: suiClient, onlyTransactionKind: true });

    // 4. Fetch key shares from Seal nodes and decrypt in one call.
    //    decrypt() internally calls fetchKeys() against the Seal key servers,
    //    which verify access via seal_approve before releasing shares.
    const aesKeyBytes = await sealClient.decrypt({
        data: encryptedKeyBytes,
        sessionKey,
        txBytes,
    });

    // 5. Return as base64 for embedding in the playback URL query param
    return btoa(String.fromCharCode(...aesKeyBytes));
}
