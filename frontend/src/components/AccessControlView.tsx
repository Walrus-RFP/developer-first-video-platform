"use client";

import React, { useState, useEffect } from "react";
import { Lock, UserPlus, Trash2, RefreshCw, ChevronDown, ChevronRight, AlertCircle, Check } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useCurrentAccount, useSignAndExecuteTransaction, useSuiClient } from "@mysten/dapp-kit";
import { Transaction } from "@mysten/sui/transactions";

const CONTROL_PLANE = (process.env.NEXT_PUBLIC_CONTROL_PLANE_URL || "http://localhost:8000") + "/v1";
const SUI_PACKAGE_ID   = process.env.NEXT_PUBLIC_SUI_PACKAGE_ID   || "0x0";
const SUI_REGISTRY_ID  = process.env.NEXT_PUBLIC_SUI_REGISTRY_ID  || "0x0";
const SUI_ACCESS_STORE = process.env.NEXT_PUBLIC_SUI_ACCESS_STORE_ID || "0x0";

const CONTRACTS_DEPLOYED = SUI_PACKAGE_ID !== "0x0";

interface GrantEntry {
    address: string;
    expires_at: string | null;
}

interface Video {
    video_id: string;
    title: string | null;
    owner: string;
    is_public: boolean;
}

interface VideoAccessPanelProps {
    video: Video;
    apiKey: string;
}

function VideoAccessPanel({ video, apiKey }: VideoAccessPanelProps) {
    const [expanded, setExpanded] = useState(false);
    const [grantees, setGrantees] = useState<GrantEntry[]>([]);
    const [loading, setLoading] = useState(false);
    const [newAddress, setNewAddress] = useState("");
    const [expiryHours, setExpiryHours] = useState("24");
    const [txMsg, setTxMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);
    const { mutateAsync: signAndExecute } = useSignAndExecuteTransaction();
    const suiClient = useSuiClient();

    // Fetch grants from the sui-auth-proxy via control plane
    const fetchGrants = async () => {
        setLoading(true);
        try {
            const res = await fetch(
                `${CONTROL_PLANE}/access/${video.video_id}/grants`,
                { headers: { "X-API-Key": apiKey } }
            );
            if (res.ok) {
                const data = await res.json();
                setGrantees(data.grants || []);
            }
        } catch {
            // Grants endpoint unavailable (contracts not deployed)
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (expanded) fetchGrants();
    }, [expanded]);

    const handleGrant = async () => {
        if (!newAddress.trim()) return;
        setTxMsg(null);

        if (!CONTRACTS_DEPLOYED) {
            setTxMsg({ type: "err", text: "Sui contracts not deployed — set SUI_PACKAGE_ID in .env.local" });
            return;
        }

        try {
            const tx = new Transaction();

            if (expiryHours && Number(expiryHours) > 0) {
                // Convert hours to Sui epoch delta (1 epoch ≈ 24 hours on testnet)
                const systemState = await suiClient.getLatestSuiSystemState();
                const currentEpoch = Number(systemState.epoch);
                const epochDelta = Math.max(1, Math.ceil(Number(expiryHours) / 24));
                const expireEpoch = currentEpoch + epochDelta;
                tx.moveCall({
                    target: `${SUI_PACKAGE_ID}::access_control::authorize_user_timed`,
                    arguments: [
                        tx.object(SUI_REGISTRY_ID),
                        tx.object(SUI_ACCESS_STORE),
                        tx.pure.string(video.video_id),
                        tx.pure.address(newAddress.trim()),
                        tx.pure.u64(expireEpoch),
                    ],
                });
            } else {
                tx.moveCall({
                    target: `${SUI_PACKAGE_ID}::access_control::authorize_user`,
                    arguments: [
                        tx.object(SUI_REGISTRY_ID),
                        tx.object(SUI_ACCESS_STORE),
                        tx.pure.string(video.video_id),
                        tx.pure.address(newAddress.trim()),
                    ],
                });
            }

            await signAndExecute({ transaction: tx });
            setTxMsg({ type: "ok", text: `Access granted to ${newAddress.slice(0, 12)}…` });
            setNewAddress("");
            await fetchGrants();
        } catch (err: any) {
            setTxMsg({ type: "err", text: err.message || "Transaction failed" });
        }
    };

    const handleRevoke = async (address: string) => {
        setTxMsg(null);

        if (!CONTRACTS_DEPLOYED) {
            setTxMsg({ type: "err", text: "Sui contracts not deployed" });
            return;
        }

        try {
            const tx = new Transaction();

            tx.moveCall({
                target: `${SUI_PACKAGE_ID}::access_control::revoke_user`,
                arguments: [
                    tx.object(SUI_REGISTRY_ID),
                    tx.object(SUI_ACCESS_STORE),
                    tx.pure.string(video.video_id),
                    tx.pure.address(address),
                ],
            });

            await signAndExecute({ transaction: tx });
            setTxMsg({ type: "ok", text: `Access revoked for ${address.slice(0, 12)}…` });
            await fetchGrants();
        } catch (err: any) {
            setTxMsg({ type: "err", text: err.message || "Revoke transaction failed" });
        }
    };

    return (
        <div className="ws-card rounded-2xl border border-white/5 overflow-hidden">
            <button
                className="w-full flex items-center justify-between p-5 hover:bg-white/5 transition-colors"
                onClick={() => setExpanded(!expanded)}
            >
                <div className="flex items-center gap-3">
                    <Lock size={16} className="text-yellow-400 flex-shrink-0" />
                    <span className="font-medium text-sm truncate">
                        {video.title || video.video_id.slice(0, 16) + "…"}
                    </span>
                    <span className="text-[10px] tracking-widest uppercase px-2 py-0.5 rounded bg-yellow-400/10 text-yellow-400 border border-yellow-400/20">
                        Private
                    </span>
                </div>
                {expanded ? <ChevronDown size={16} className="text-muted" /> : <ChevronRight size={16} className="text-muted" />}
            </button>

            <AnimatePresence>
                {expanded && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                    >
                        <div className="px-5 pb-5 space-y-4 border-t border-white/5 pt-4">
                            {/* Grant new access */}
                            <div className="space-y-3">
                                <p className="text-xs text-muted uppercase tracking-widest font-semibold">Grant Access</p>
                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        value={newAddress}
                                        onChange={e => setNewAddress(e.target.value)}
                                        placeholder="0x wallet address…"
                                        className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-sm text-white placeholder:text-muted focus:outline-none focus:border-white/30"
                                    />
                                    <input
                                        type="number"
                                        value={expiryHours}
                                        onChange={e => setExpiryHours(e.target.value)}
                                        placeholder="hrs"
                                        title="Expiry in hours (0 = permanent)"
                                        className="w-20 bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder:text-muted focus:outline-none focus:border-white/30 text-center"
                                    />
                                    <button
                                        onClick={handleGrant}
                                        disabled={!newAddress.trim()}
                                        className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white text-black text-sm font-semibold hover:bg-white/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                                    >
                                        <UserPlus size={14} /> Grant
                                    </button>
                                </div>
                                <p className="text-[11px] text-muted">
                                    Expiry in hours. Leave 0 for permanent access.
                                    {!CONTRACTS_DEPLOYED && (
                                        <span className="text-yellow-400 ml-1">Sui contracts not deployed — grants will be simulated.</span>
                                    )}
                                </p>
                            </div>

                            {/* Tx feedback */}
                            <AnimatePresence>
                                {txMsg && (
                                    <motion.div
                                        initial={{ opacity: 0, y: -4 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0 }}
                                        className={`flex items-center gap-2 text-xs px-3 py-2 rounded-lg ${
                                            txMsg.type === "ok"
                                                ? "bg-green-500/10 text-green-400 border border-green-500/20"
                                                : "bg-red-500/10 text-red-400 border border-red-500/20"
                                        }`}
                                    >
                                        {txMsg.type === "ok" ? <Check size={12} /> : <AlertCircle size={12} />}
                                        {txMsg.text}
                                    </motion.div>
                                )}
                            </AnimatePresence>

                            {/* Current grantees */}
                            <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                    <p className="text-xs text-muted uppercase tracking-widest font-semibold">Current Grantees</p>
                                    <button onClick={fetchGrants} className="text-muted hover:text-white transition-colors">
                                        <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
                                    </button>
                                </div>
                                {loading ? (
                                    <p className="text-xs text-muted py-2">Loading…</p>
                                ) : grantees.length === 0 ? (
                                    <p className="text-xs text-muted py-2">No grantees yet.</p>
                                ) : (
                                    <div className="space-y-1">
                                        {grantees.map(g => (
                                            <div key={g.address} className="flex items-center justify-between bg-white/5 rounded-xl px-3 py-2">
                                                <div>
                                                    <p className="text-xs font-mono text-white/80">
                                                        {g.address.slice(0, 18)}…
                                                    </p>
                                                    {g.expires_at && (
                                                        <p className="text-[10px] text-muted">
                                                            Expires {new Date(Number(g.expires_at)).toLocaleString()}
                                                        </p>
                                                    )}
                                                </div>
                                                <button
                                                    onClick={() => handleRevoke(g.address)}
                                                    className="text-red-400/60 hover:text-red-400 transition-colors"
                                                    title="Revoke access"
                                                >
                                                    <Trash2 size={14} />
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}


interface AccessControlViewProps {
    address: string;
}

export default function AccessControlView({ address }: AccessControlViewProps) {
    const [privateVideos, setPrivateVideos] = useState<Video[]>([]);
    const [loading, setLoading] = useState(true);
    const [apiKey, setApiKey] = useState("");
    const [apiKeyInput, setApiKeyInput] = useState("");

    const fetchPrivateVideos = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${CONTROL_PLANE}/videos?owner=${address}`);
            if (res.ok) {
                const data = await res.json();
                const priv = (data.videos || []).filter((v: Video) => !v.is_public);
                setPrivateVideos(priv);
            }
        } catch { }
        finally { setLoading(false); }
    };

    useEffect(() => {
        fetchPrivateVideos();
    }, [address]);

    if (!apiKey) {
        return (
            <div className="space-y-6 max-w-lg">
                <div className="space-y-1">
                    <h3 className="text-lg font-bold">Access Control</h3>
                    <p className="text-muted text-sm">Manage who can watch your private videos.</p>
                </div>
                <div className="ws-card rounded-2xl p-6 border border-white/5 space-y-4">
                    <p className="text-sm text-muted">Enter your API key to manage access grants:</p>
                    <div className="flex gap-3">
                        <input
                            type="text"
                            value={apiKeyInput}
                            onChange={e => setApiKeyInput(e.target.value)}
                            placeholder="cv_…"
                            className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-sm text-white placeholder:text-muted focus:outline-none focus:border-white/30"
                        />
                        <button
                            onClick={() => setApiKey(apiKeyInput.trim())}
                            disabled={!apiKeyInput.trim().startsWith("cv_")}
                            className="px-4 py-2 rounded-xl bg-white text-black text-sm font-semibold hover:bg-white/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                            Unlock
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div className="space-y-1">
                    <h3 className="text-lg font-bold">Access Control</h3>
                    <p className="text-muted text-sm">
                        {privateVideos.length} private video{privateVideos.length !== 1 ? "s" : ""} — grant or revoke viewer access on-chain.
                    </p>
                </div>
                <button onClick={fetchPrivateVideos} className="text-muted hover:text-white transition-colors">
                    <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
                </button>
            </div>

            {!CONTRACTS_DEPLOYED && (
                <div className="flex items-start gap-3 bg-yellow-400/5 border border-yellow-400/20 rounded-2xl p-4 text-sm text-yellow-300">
                    <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
                    <p>
                        Sui contracts not deployed. Set <code className="font-mono text-xs bg-white/10 px-1 py-0.5 rounded">NEXT_PUBLIC_SUI_PACKAGE_ID</code>,{" "}
                        <code className="font-mono text-xs bg-white/10 px-1 py-0.5 rounded">NEXT_PUBLIC_SUI_REGISTRY_ID</code>, and{" "}
                        <code className="font-mono text-xs bg-white/10 px-1 py-0.5 rounded">NEXT_PUBLIC_SUI_ACCESS_STORE_ID</code> in <code className="font-mono text-xs bg-white/10 px-1 py-0.5 rounded">.env.local</code> after deploying.
                    </p>
                </div>
            )}

            {loading ? (
                <div className="space-y-3">
                    {[1, 2].map(i => <div key={i} className="h-14 bg-white/5 animate-pulse rounded-2xl" />)}
                </div>
            ) : privateVideos.length === 0 ? (
                <div className="py-16 text-center border border-dashed border-white/10 rounded-2xl">
                    <Lock size={32} className="text-muted mx-auto mb-3" />
                    <p className="text-muted text-sm">No private videos found.</p>
                    <p className="text-muted text-xs mt-1">Upload a video and set it to private to manage access here.</p>
                </div>
            ) : (
                <div className="space-y-3">
                    {privateVideos.map(v => (
                        <VideoAccessPanel key={v.video_id} video={v} apiKey={apiKey} />
                    ))}
                </div>
            )}
        </div>
    );
}
