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
const SUI_PACKAGE_ID    = process.env.NEXT_PUBLIC_SUI_PACKAGE_ID    || "";
const SUI_ACCESS_STORE  = process.env.NEXT_PUBLIC_SUI_ACCESS_STORE_ID || "";

interface SubscriptionOffer {
    videoId: string;
    videoTitle: string;
    priceMist: number;
    durationEpochs: number;
    revenueAddress: string;
}

export default function Home() {
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
        console.log(`[Frontend] Fetching videos for ${type}...`);
        try {
            setLoading(true);
            const url = type === 'mine' && account
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

    useEffect(() => {
        fetchVideos(viewType);
    }, [viewType, account?.address]);

    const handlePurchaseSubscription = async () => {
        if (!subscriptionOffer || !account || !SUI_PACKAGE_ID || !SUI_ACCESS_STORE) return;
        setPurchasing(true);
        try {
            const tx = new Transaction();
            const [paymentCoin] = tx.splitCoins(tx.gas, [tx.pure.u64(subscriptionOffer.priceMist)]);
            tx.moveCall({
                target: `${SUI_PACKAGE_ID}::access_control::purchase_access`,
                arguments: [
                    tx.object(SUI_ACCESS_STORE),
                    tx.pure.string(subscriptionOffer.videoId),
                    paymentCoin,
                ],
            });
            await signAndExecuteTransaction({ transaction: tx });
            const videoId = subscriptionOffer.videoId;
            setSubscriptionOffer(null);
            // Retry playback now that access is granted
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
                    // Check if there's a subscription policy available
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

            // Seal-encrypted video: decrypt key via Mysten Seal SDK
            if (data.needs_seal) {
                if (!account) throw new Error("Connect your wallet to play this Seal-encrypted video.");
                const { seal_key_blob_id } = data;

                // Fetch the Seal-encrypted key blob from the data plane
                const DATA_PLANE = (process.env.NEXT_PUBLIC_DATA_PLANE_URL || "http://127.0.0.1:8001");
                const blobRes = await fetch(`${DATA_PLANE}/v1/seal-blob/${seal_key_blob_id}`);
                if (!blobRes.ok) throw new Error("Failed to fetch Seal key blob");
                const encryptedKeyBytes = new Uint8Array(await blobRes.arrayBuffer());

                // Dynamically import Seal utilities
                const { sealDecryptVideoKey } = await import("@/lib/seal");

                // NOTE: suiClient and signPersonalMessage come from component-scope hooks.
                // In production, consider passing these via React context if the component tree grows.
                const sealKey = await sealDecryptVideoKey(
                    suiClient,
                    videoId,
                    encryptedKeyBytes,
                    account.address,
                    signPersonalMessage,
                );

                // Re-request playback URL with decrypted key
                const resolvedRes = await fetch(
                    `${API_BASE}/playback-url/${videoId}?user_address=${account.address}&seal_key=${encodeURIComponent(sealKey)}`
                );
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
        <div className="px-6 py-12 max-w-7xl mx-auto space-y-24">
            {/* Hero Section */}
            <section className="space-y-8">
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.8 }}
                    className="space-y-4 max-w-2xl"
                >
                    <h1 className="text-5xl md:text-7xl font-bold tracking-tighter leading-none">
                        STREAMING WITHOUT <br /> LIMITS.
                    </h1>
                    <p className="text-muted text-lg max-w-md">
                        Decentralized video delivery at the speed of Sui. Pure, stateless, and developer-first.
                    </p>
                </motion.div>

                <div className="flex gap-4">
                    <button
                        onClick={() => setShowUpload(true)}
                        className="btn-primary flex items-center gap-2"
                    >
                        <Plus size={18} /> Upload Video
                    </button>
                    <button className="btn-secondary">Explore Network</button>
                </div>
            </section>

            {/* Platform Stats */}
            <DashboardStats />

            {/* Video Grid */}
            <section className="space-y-8">
                <div className="flex flex-col md:flex-row items-start md:items-end justify-between border-b border-white/5 pb-4 gap-4">
                    <div className="flex gap-6">
                        <button
                            onClick={() => setViewType("all")}
                            className={`text-sm font-semibold tracking-widest uppercase transition-colors ${viewType === 'all' ? 'text-white' : 'text-muted hover:text-white/70'}`}
                        >
                            Global Feed
                        </button>
                        <button
                            onClick={() => setViewType("mine")}
                            className={`text-sm font-semibold tracking-widest uppercase transition-colors ${viewType === 'mine' ? 'text-white' : 'text-muted hover:text-white/70'}`}
                        >
                            My Library
                        </button>
                        {account && (
                            <button
                                onClick={() => setViewType("api_keys")}
                                className={`text-sm font-semibold tracking-widest uppercase transition-colors ${viewType === 'api_keys' ? 'text-white' : 'text-muted hover:text-white/70'}`}
                            >
                                API Keys
                            </button>
                        )}
                        {account && (
                            <button
                                onClick={() => setViewType("access")}
                                className={`text-sm font-semibold tracking-widest uppercase transition-colors ${viewType === 'access' ? 'text-white' : 'text-muted hover:text-white/70'}`}
                            >
                                Access Control
                            </button>
                        )}
                    </div>
                    {viewType !== 'api_keys' && viewType !== 'access' && (
                        <span className="text-xs text-muted tracking-tight">{videos.length} videos available</span>
                    )}
                </div>

                {viewType === 'api_keys' && account ? (
                    <ApiKeysView address={account.address} />
                ) : viewType === 'access' && account ? (
                    <AccessControlView address={account.address} />
                ) : viewType === 'mine' && !account ? (
                    <div className="py-20 text-center border border-dashed border-white/10 rounded-2xl glass-card">
                        <div className="w-16 h-16 bg-white/5 rounded-full flex items-center justify-center mx-auto mb-4">
                            <Info className="text-muted" size={24} />
                        </div>
                        <h3 className="text-xl font-bold mb-2">Wallet Disconnected</h3>
                        <p className="text-muted max-w-sm mx-auto">Please connect your Slush wallet using the button above to view and manage your private video assets.</p>
                    </div>
                ) : loading ? (
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                        {[1, 2, 3].map(i => (
                            <div key={i} className="aspect-video bg-white/5 animate-pulse rounded-lg" />
                        ))}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-12">
                        {videos.map((vid, idx) => (
                            <VideoCard
                                key={vid.video_id}
                                video={vid}
                                index={idx}
                                onClick={() => handlePlay(vid.video_id)}
                            />
                        ))}
                        {videos.length === 0 && (
                            <div className="col-span-full py-20 text-center border border-dashed border-white/10 rounded-2xl">
                                <p className="text-muted">No videos found. Start by uploading your first asset.</p>
                            </div>
                        )}
                    </div>
                )}
            </section>

            {/* Modals */}
            <AnimatePresence>
                {showUpload && (
                    <UploadModal
                        onClose={() => setShowUpload(false)}
                        onSuccess={fetchVideos}
                    />
                )}
                {activePlayback && (
                    <VideoPlayer
                        videoId={activePlayback.id}
                        playbackUrl={activePlayback.url}
                        onClose={() => setActivePlayback(null)}
                    />
                )}
                {subscriptionOffer && (
                    <div className="fixed inset-0 z-[100] bg-black/80 backdrop-blur-md flex items-center justify-center p-6">
                        <motion.div
                            initial={{ scale: 0.95, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            className="w-full max-w-md glass-card rounded-3xl p-10 space-y-6"
                        >
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-full bg-yellow-400/10 flex items-center justify-center">
                                    <Lock size={18} className="text-yellow-400" />
                                </div>
                                <div>
                                    <h2 className="text-xl font-bold tracking-tight">Private Content</h2>
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
                            <p className="text-xs text-muted">
                                Your wallet will sign a Sui transaction to purchase time-limited access. SUI is sent directly to the content owner.
                            </p>
                            <div className="flex gap-3">
                                <button
                                    onClick={handlePurchaseSubscription}
                                    disabled={purchasing || !account}
                                    className="btn-primary flex-1 flex items-center justify-center gap-2 disabled:opacity-40"
                                >
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

function VideoCard({ video, index, onClick }: { video: any, index: number, onClick: () => void }) {
    const displayTitle = video.title || `Video ${video.video_id.slice(0, 8)}`;

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: index * 0.1 }}
            onClick={onClick}
            className="group cursor-pointer space-y-4"
        >
            <div className="relative aspect-video glass-card rounded-2xl overflow-hidden group-hover:border-white/20 transition-all duration-500 bg-white/5">
                <img
                    src={`${process.env.NEXT_PUBLIC_CONTROL_PLANE_URL}/v1/thumbnail/${video.video_id}`}
                    alt={displayTitle}
                    className="absolute inset-0 w-full h-full object-cover"
                    onError={(e) => {
                        e.currentTarget.style.display = 'none';
                    }}
                />
                <div className="absolute inset-0 bg-black/40 group-hover:bg-black/20 transition-colors" />
                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-500 scale-90 group-hover:scale-100">
                    <div className="w-16 h-16 bg-white rounded-full flex items-center justify-center text-black">
                        <Play fill="currentColor" size={24} className="ml-1" />
                    </div>
                </div>
                {video.duration_seconds && (
                    <div className="absolute bottom-4 left-4 text-[10px] tracking-widest font-bold uppercase py-1 px-2 border border-white/20 rounded bg-black/40 backdrop-blur-md">
                        {formatDuration(video.duration_seconds)}
                    </div>
                )}
                <div className="absolute bottom-4 right-4 flex gap-2">
                    {video.resolution && (
                        <span className="text-[10px] tracking-widest font-bold uppercase py-1 px-2 border border-white/20 rounded bg-black/40 backdrop-blur-md">
                            {video.resolution}
                        </span>
                    )}
                    <span className="text-[10px] tracking-widest font-bold uppercase py-1 px-2 border border-white/20 rounded bg-black/40 backdrop-blur-md">
                        {video.status}
                    </span>
                </div>
            </div>
            <div className="space-y-1">
                <div className="flex justify-between items-start">
                    <h3 className="font-medium tracking-tight truncate flex-1">{displayTitle}</h3>
                    <ArrowUpRight size={14} className="opacity-0 group-hover:opacity-40 transition-opacity" />
                </div>
                <p className="text-xs text-muted truncate">
                    {video.owner !== "test_user" ? video.owner.slice(0, 10) + "…" : "Anonymous"}
                    {video.file_size ? ` · ${formatSize(video.file_size)}` : ""}
                </p>
            </div>
        </motion.div>
    );
}
