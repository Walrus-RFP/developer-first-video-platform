"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Plus, Play, Info, ArrowUpRight, Lock, Loader2 } from "lucide-react";
import { useState, useEffect } from "react";
import { useCurrentAccount, useSuiClient, useSignPersonalMessage, useSignAndExecuteTransaction } from "@mysten/dapp-kit";
import { Transaction } from "@mysten/sui/transactions";
import UploadModal from "@/components/UploadModal";
import VideoPlayer from "@/components/VideoPlayer";
import ApiKeysView from "@/components/ApiKeysView";
import AccessControlView from "@/components/AccessControlView";
import DashboardStats from "@/components/DashboardStats";

const API_BASE = (process.env.NEXT_PUBLIC_CONTROL_PLANE_URL || "http://127.0.0.1:8000") + "/v1";
const SUI_PACKAGE_ID   = process.env.NEXT_PUBLIC_SUI_PACKAGE_ID    || "";
const SUI_ACCESS_STORE = process.env.NEXT_PUBLIC_SUI_ACCESS_STORE_ID || "";

interface SubscriptionOffer {
    videoId: string;
    videoTitle: string;
    priceMist: number;
    durationEpochs: number;
    revenueAddress: string;
}

export default function Dashboard() {
    const [videos, setVideos] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [viewType, setViewType] = useState<"all" | "mine" | "api_keys" | "access">("all");
    const [showUpload, setShowUpload] = useState(false);
    const [activePlayback, setActivePlayback] = useState<{ id: string, url: string } | null>(null);
    const [subscriptionOffer, setSubscriptionOffer] = useState<SubscriptionOffer | null>(null);
    const [purchasing, setPurchasing] = useState(false);
    const account = useCurrentAccount();
    const suiClient = useSuiClient();
    const { mutateAsync: signPersonalMessage } = useSignPersonalMessage();
    const { mutateAsync: signAndExecuteTransaction } = useSignAndExecuteTransaction();

    const fetchVideos = async (type = viewType) => {
        try {
            setLoading(true);
            const url = type === "mine" && account
                ? `${API_BASE}/videos?owner=${account.address}`
                : `${API_BASE}/videos`;
            const res = await fetch(url);
            const data = await res.json();
            setVideos(data.videos || []);
        } catch (err) {
            console.error("Failed to fetch videos", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchVideos(viewType); }, [viewType, account?.address]);

    const handlePurchaseSubscription = async () => {
        if (!subscriptionOffer || !account || !SUI_PACKAGE_ID || !SUI_ACCESS_STORE) return;
        setPurchasing(true);
        try {
            const tx = new Transaction();
            const [paymentCoin] = tx.splitCoins(tx.gas, [tx.pure.u64(subscriptionOffer.priceMist)]);
            tx.moveCall({
                target: `${SUI_PACKAGE_ID}::access_control::purchase_access`,
                arguments: [tx.object(SUI_ACCESS_STORE), tx.pure.string(subscriptionOffer.videoId), paymentCoin],
            });
            await signAndExecuteTransaction({ transaction: tx });
            const videoId = subscriptionOffer.videoId;
            setSubscriptionOffer(null);
            await handlePlay(videoId);
        } catch (err: any) {
            alert(err.message || "Purchase failed.");
        } finally {
            setPurchasing(false);
        }
    };

    const handlePlay = async (videoId: string) => {
        try {
            const url = account
                ? `${API_BASE}/playback-url/${videoId}?user_address=${account.address}`
                : `${API_BASE}/playback-url/${videoId}`;
            const res = await fetch(url);
            if (!res.ok) {
                if (res.status === 403) {
                    const subRes = await fetch(`${API_BASE}/subscription/${videoId}`).catch(() => null);
                    if (subRes?.ok) {
                        const sub = await subRes.json();
                        if (sub.has_policy && sub.price_mist > 0) {
                            const vid = videos.find(v => v.video_id === videoId);
                            setSubscriptionOffer({
                                videoId,
                                videoTitle: vid?.title || videoId.slice(0, 8) + "…",
                                priceMist: sub.price_mist,
                                durationEpochs: sub.duration_epochs,
                                revenueAddress: sub.revenue_address,
                            });
                            return;
                        }
                    }
                    throw new Error("Permission denied. Ensure wallet holds access policy.");
                }
                throw new Error("Playback failed");
            }
            const data = await res.json();
            if (data.needs_seal) {
                if (!account) throw new Error("Connect your wallet to play this Seal-encrypted video.");
                const DATA_PLANE = (process.env.NEXT_PUBLIC_DATA_PLANE_URL || "http://127.0.0.1:8001");
                const blobRes = await fetch(`${DATA_PLANE}/v1/seal-blob/${data.seal_key_blob_id}`);
                if (!blobRes.ok) throw new Error("Failed to fetch Seal key blob");
                const encryptedKeyBytes = new Uint8Array(await blobRes.arrayBuffer());
                const { sealDecryptVideoKey } = await import("@/lib/seal");
                const sealKey = await sealDecryptVideoKey(suiClient, videoId, encryptedKeyBytes, account.address, signPersonalMessage);
                const resolvedRes = await fetch(`${API_BASE}/playback-url/${videoId}?user_address=${account.address}&seal_key=${encodeURIComponent(sealKey)}`);
                if (!resolvedRes.ok) throw new Error("Failed to get resolved playback URL");
                const resolvedData = await resolvedRes.json();
                setActivePlayback({ id: videoId, url: resolvedData.playlist });
                return;
            }
            setActivePlayback({ id: videoId, url: data.playlist });
        } catch (err: any) {
            alert(err.message || "Failed to get playback authorization.");
        }
    };

    return (
        <div className="max-w-7xl mx-auto px-6 py-12 space-y-12">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="font-display text-4xl">Dashboard</h1>
                    <p className="text-muted text-sm mt-1">Your videos, keys, and access controls.</p>
                </div>
                <button onClick={() => setShowUpload(true)} className="btn-primary flex items-center gap-2">
                    <Plus size={16} /> Upload Video
                </button>
            </div>

            {/* Stats */}
            <DashboardStats />

            {/* Video Grid */}
            <section className="space-y-6">
                <div className="flex flex-col md:flex-row items-start md:items-end justify-between border-b border-white/5 pb-4 gap-4">
                    <div className="flex gap-6">
                        {(["all", "mine", ...(account ? ["api_keys", "access"] : [])] as ("all" | "mine" | "api_keys" | "access")[]).map((type) => {
                            const labels: Record<string, string> = { all: "Global Feed", mine: "My Library", api_keys: "API Keys", access: "Access Control" };
                            const colors: Record<string, string> = { all: "#E8372C", mine: "#F5C518", api_keys: "#2E5CE6", access: "#2D9448" };
                            return (
                                <button
                                    key={type}
                                    onClick={() => setViewType(type)}
                                    className={`text-sm font-semibold tracking-widest uppercase transition-colors pb-1 border-b-2 ${viewType === type ? "text-white" : "border-transparent text-muted hover:text-white/70"}`}
                                    style={viewType === type ? { borderBottomColor: colors[type] } : {}}
                                >
                                    {labels[type]}
                                </button>
                            );
                        })}
                    </div>
                    {viewType !== "api_keys" && viewType !== "access" && (
                        <span className="text-xs text-muted">{videos.length} {videos.length === 1 ? "video" : "videos"} available</span>
                    )}
                </div>

                {viewType === "api_keys" && account ? (
                    <ApiKeysView address={account.address} />
                ) : viewType === "access" && account ? (
                    <AccessControlView address={account.address} />
                ) : viewType === "mine" && !account ? (
                    <div className="py-20 text-center border border-dashed border-white/10 rounded-2xl ws-card">
                        <div className="w-16 h-16 bg-white/5 rounded-full flex items-center justify-center mx-auto mb-4">
                            <Info className="text-muted" size={24} />
                        </div>
                        <h3 className="font-display text-2xl mb-2">Wallet Disconnected</h3>
                        <p className="text-muted max-w-sm mx-auto">Connect your Slush wallet to view and manage your private video assets.</p>
                    </div>
                ) : loading ? (
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {[1, 2, 3].map(i => <div key={i} className="aspect-video bg-white/5 animate-pulse rounded-xl" />)}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {videos.map((vid, idx) => (
                            <VideoCard key={vid.video_id} video={vid} index={idx} onClick={() => handlePlay(vid.video_id)} />
                        ))}
                        {videos.length === 0 && (
                            <div className="col-span-full py-20 text-center border border-dashed border-white/10 rounded-2xl ws-card">
                                <p className="text-muted">No videos yet. Upload your first asset.</p>
                            </div>
                        )}
                    </div>
                )}
            </section>

            {/* Modals */}
            <AnimatePresence>
                {showUpload && <UploadModal onClose={() => setShowUpload(false)} onSuccess={fetchVideos} />}
                {activePlayback && <VideoPlayer videoId={activePlayback.id} playbackUrl={activePlayback.url} onClose={() => setActivePlayback(null)} />}
                {subscriptionOffer && (
                    <div className="fixed inset-0 z-[100] bg-black/80 backdrop-blur-md flex items-center justify-center p-6">
                        <motion.div
                            initial={{ scale: 0.95, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            className="w-full max-w-md ws-card ws-card-yellow rounded-3xl p-10 space-y-6"
                        >
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-full bg-yellow-400/10 flex items-center justify-center">
                                    <Lock size={18} className="text-yellow-400" />
                                </div>
                                <div>
                                    <h2 className="font-display text-2xl">Private Content</h2>
                                    <p className="text-muted text-sm truncate">{subscriptionOffer.videoTitle}</p>
                                </div>
                            </div>
                            <div className="bg-white/5 border border-white/10 rounded-2xl p-5 space-y-3">
                                <div className="flex justify-between text-sm">
                                    <span className="text-muted">Price</span>
                                    <span className="font-bold">{(subscriptionOffer.priceMist / 1_000_000_000).toFixed(4)} SUI</span>
                                </div>
                                <div className="flex justify-between text-sm">
                                    <span className="text-muted">Access duration</span>
                                    <span className="font-bold">{subscriptionOffer.durationEpochs} epoch{subscriptionOffer.durationEpochs !== 1 ? "s" : ""} (~{subscriptionOffer.durationEpochs} day{subscriptionOffer.durationEpochs !== 1 ? "s" : ""})</span>
                                </div>
                            </div>
                            <p className="text-xs text-muted">Your wallet will sign a Sui transaction. SUI is sent directly to the content owner.</p>
                            <div className="flex gap-3">
                                <button onClick={handlePurchaseSubscription} disabled={purchasing || !account} className="btn-primary flex-1 flex items-center justify-center gap-2 disabled:opacity-40">
                                    {purchasing ? <Loader2 size={16} className="animate-spin" /> : <Lock size={16} />}
                                    {purchasing ? "Purchasing…" : "Buy Access"}
                                </button>
                                <button onClick={() => setSubscriptionOffer(null)} className="btn-secondary">Cancel</button>
                            </div>
                            {!account && <p className="text-xs text-yellow-400 text-center">Connect your wallet to purchase access.</p>}
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>
        </div>
    );
}

const CARD_COLORS = [
    { border: "#E8372C", tag: "ws-tag ws-tag-red" },
    { border: "#F5C518", tag: "ws-tag ws-tag-yellow" },
    { border: "#2E5CE6", tag: "ws-tag ws-tag-blue" },
    { border: "#2D9448", tag: "ws-tag ws-tag-green" },
];

function formatDuration(seconds: number | null): string {
    if (!seconds) return "";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
}

function formatSize(bytes: number | null): string {
    if (!bytes) return "";
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function VideoCard({ video, index, onClick }: { video: any; index: number; onClick: () => void }) {
    const displayTitle = video.title || `Video ${video.video_id.slice(0, 8)}`;
    const color = CARD_COLORS[index % CARD_COLORS.length];
    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: index * 0.1 }}
            onClick={onClick}
            className="group cursor-pointer space-y-3"
        >
            <div className="relative aspect-video ws-card rounded-xl overflow-hidden transition-all duration-500" style={{ borderTop: `2px solid ${color.border}` }}>
                <img
                    src={`${process.env.NEXT_PUBLIC_CONTROL_PLANE_URL}/v1/thumbnail/${video.video_id}`}
                    alt={displayTitle}
                    className="absolute inset-0 w-full h-full object-cover"
                    onError={(e) => { e.currentTarget.style.display = "none"; }}
                />
                <div className="absolute inset-0 bg-black/40 group-hover:bg-black/20 transition-colors" />
                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-300 scale-90 group-hover:scale-100">
                    <div className="w-14 h-14 rounded-full flex items-center justify-center text-white" style={{ background: color.border }}>
                        <Play fill="currentColor" size={20} className="ml-0.5" />
                    </div>
                </div>
                {video.duration_seconds && (
                    <div className="absolute bottom-3 left-3 text-[10px] tracking-widest font-bold uppercase py-0.5 px-2 border border-white/20 rounded bg-black/50 backdrop-blur-sm">
                        {formatDuration(video.duration_seconds)}
                    </div>
                )}
                <div className="absolute bottom-3 right-3 flex gap-1.5">
                    {video.resolution && <span className={color.tag}>{video.resolution}</span>}
                    <span className="ws-tag" style={{ background: "rgba(255,255,255,0.08)", color: "#888" }}>{video.status}</span>
                </div>
            </div>
            <div className="space-y-0.5">
                <div className="flex justify-between items-center">
                    <h3 className="font-semibold text-sm tracking-tight truncate flex-1">{displayTitle}</h3>
                    <ArrowUpRight size={13} className="opacity-0 group-hover:opacity-40 transition-opacity ml-2 shrink-0" />
                </div>
                <p className="text-xs text-muted truncate">
                    {video.owner !== "test_user" ? video.owner.slice(0, 10) + "…" : "Anonymous"}
                    {video.file_size ? ` · ${formatSize(video.file_size)}` : ""}
                </p>
            </div>
        </motion.div>
    );
}
