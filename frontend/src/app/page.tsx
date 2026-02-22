"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Plus, Play, Info, ArrowUpRight } from "lucide-react";
import { useState, useEffect } from "react";
import { useCurrentAccount } from "@mysten/dapp-kit";
import UploadModal from "@/components/UploadModal";
import VideoPlayer from "@/components/VideoPlayer";

const API_BASE = "http://127.0.0.1:8000";

export default function Home() {
    const [videos, setVideos] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [viewType, setViewType] = useState<"all" | "mine">("all");
    const [showUpload, setShowUpload] = useState(false);
    const [activePlayback, setActivePlayback] = useState<{ id: string, url: string } | null>(null);
    const account = useCurrentAccount();

    const fetchVideos = async (type = viewType) => {
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
    }, [viewType, account]);

    const handlePlay = async (videoId: string) => {
        try {
            const url = account ? `${API_BASE}/playback-url/${videoId}?user_address=${account.address}` : `${API_BASE}/playback-url/${videoId}`;
            const res = await fetch(url);
            if (!res.ok) {
                if (res.status === 403) throw new Error("Permission denied. Ensure wallet holds access policy.");
                throw new Error("Playback failed");
            }
            const data = await res.json();
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
                    </div>
                    <span className="text-xs text-muted tracking-tight">{videos.length} videos available</span>
                </div>

                {viewType === 'mine' && !account ? (
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
            </AnimatePresence>
        </div>
    );
}

function VideoCard({ video, index, onClick }: { video: any, index: number, onClick: () => void }) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: index * 0.1 }}
            onClick={onClick}
            className="group cursor-pointer space-y-4"
        >
            <div className="relative aspect-video glass-card rounded-2xl overflow-hidden group-hover:border-white/20 transition-all duration-500">
                <div className="absolute inset-0 bg-gradient-to-br from-white/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-500 scale-90 group-hover:scale-100">
                    <div className="w-16 h-16 bg-white rounded-full flex items-center justify-center text-black">
                        <Play fill="currentColor" size={24} className="ml-1" />
                    </div>
                </div>
                <div className="absolute bottom-4 right-4 text-[10px] tracking-widest font-bold uppercase py-1 px-2 border border-white/20 rounded bg-black/40 backdrop-blur-md">
                    {video.status}
                </div>
            </div>
            <div className="space-y-1">
                <div className="flex justify-between items-start">
                    <h3 className="font-medium tracking-tight truncate flex-1">{video.video_id}</h3>
                    <ArrowUpRight size={14} className="opacity-0 group-hover:opacity-40 transition-opacity" />
                </div>
                <p className="text-xs text-muted truncate">{video.file_path}</p>
            </div>
        </motion.div>
    );
}
