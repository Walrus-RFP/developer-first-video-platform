"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import Hls from "hls.js";
import { Play, Pause, Volume2, VolumeX, Maximize, X, Copy, Check, Code2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface VideoPlayerProps {
    videoId: string;
    playbackUrl: string;
    onClose: () => void;
}

export default function VideoPlayer({ videoId, playbackUrl, onClose }: VideoPlayerProps) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const progressRef = useRef<HTMLDivElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [progress, setProgress] = useState(0);
    const [volume, setVolume] = useState(1);
    const [isMuted, setIsMuted] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [tab, setTab] = useState<"iframe" | "react" | "hlsjs">("iframe");
    const [copied, setCopied] = useState(false);
    const [embedUrl, setEmbedUrl] = useState<string | null>(null);

    const CONTROL_PLANE = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL || "http://localhost:8000";

    // Fetch the stable embed URL from control plane (not the expiring signed URL)
    useEffect(() => {
        fetch(`${CONTROL_PLANE}/v1/videos/${videoId}/embed`)
            .then(r => r.ok ? r.json() : null)
            .then(data => { if (data?.embed_url) setEmbedUrl(data.embed_url); })
            .catch(() => {});
    }, [videoId, CONTROL_PLANE]);

    useEffect(() => {
        let isMounted = true;
        const video = videoRef.current;
        if (!video) return;

        const playVideo = async () => {
            try {
                if (isMounted && video.paused) {
                    await video.play();
                    if (isMounted) setIsPlaying(true);
                }
            } catch (err: any) {
                if (err.name !== "AbortError") console.error("Playback failed", err);
            }
        };

        if (Hls.isSupported()) {
            const hls = new Hls({ xhrSetup: (xhr) => { xhr.withCredentials = false; } });
            hls.loadSource(playbackUrl);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, playVideo);
            hls.on(Hls.Events.ERROR, (_, data) => {
                if (data.fatal) console.error("HLS Fatal Error:", data.type, data.details);
            });
            return () => { isMounted = false; hls.destroy(); };
        } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
            video.src = playbackUrl;
            video.addEventListener("loadedmetadata", playVideo);
            return () => { isMounted = false; };
        }
    }, [playbackUrl]);

    const togglePlay = () => {
        if (!videoRef.current) return;
        if (isPlaying) videoRef.current.pause();
        else videoRef.current.play();
        setIsPlaying(!isPlaying);
    };

    const handleTimeUpdate = () => {
        const video = videoRef.current;
        if (!video) return;
        const dur = video.duration || 0;
        const cur = video.currentTime || 0;
        setCurrentTime(cur);
        setDuration(dur);
        setProgress(dur > 0 ? (cur / dur) * 100 : 0);
    };

    const handleLoadedMetadata = () => {
        if (videoRef.current) setDuration(videoRef.current.duration || 0);
    };

    const handleProgressClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
        if (!progressRef.current || !videoRef.current) return;
        const rect = progressRef.current.getBoundingClientRect();
        const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        videoRef.current.currentTime = pct * (videoRef.current.duration || 0);
        setProgress(pct * 100);
    }, []);

    const handleVolumeClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
        if (!videoRef.current) return;
        const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
        const newVol = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        videoRef.current.volume = newVol;
        videoRef.current.muted = newVol === 0;
        setVolume(newVol);
        setIsMuted(newVol === 0);
    }, []);

    const toggleMute = () => {
        if (!videoRef.current) return;
        const newMuted = !isMuted;
        videoRef.current.muted = newMuted;
        setIsMuted(newMuted);
    };

    const handleFullscreen = () => {
        if (!containerRef.current) return;
        if (!document.fullscreenElement) {
            containerRef.current.requestFullscreen().catch(console.error);
        } else {
            document.exitFullscreen().catch(console.error);
        }
    };

    const formatTime = (s: number) => {
        if (!isFinite(s) || isNaN(s)) return "0:00";
        const m = Math.floor(s / 60);
        const sec = Math.floor(s % 60);
        return `${m}:${sec.toString().padStart(2, "0")}`;
    };

    const effectiveEmbedUrl = embedUrl || playbackUrl;

    const getSnippet = () => {
        if (tab === "iframe") {
            return `<iframe\n  src="${effectiveEmbedUrl}"\n  style="width: 100%; aspect-ratio: 16/9; border: none;"\n  allow="autoplay; fullscreen; encrypted-media"\n  allowfullscreen\n></iframe>`;
        }
        if (tab === "react") {
            return `import { useEffect, useRef } from 'react';\nimport Hls from 'hls.js';\n\nexport default function Video() {\n  const ref = useRef(null);\n  useEffect(() => {\n    if (Hls.isSupported()) {\n      const hls = new Hls();\n      hls.loadSource('${playbackUrl}');\n      hls.attachMedia(ref.current);\n    }\n  }, []);\n  return <video ref={ref} controls className="w-full aspect-video" />;\n}`;
        }
        if (tab === "hlsjs") {
            return `import Hls from 'hls.js';\n\nconst video = document.getElementById('video');\nif (Hls.isSupported()) {\n  const hls = new Hls();\n  hls.loadSource('${playbackUrl}');\n  hls.attachMedia(video);\n  hls.on(Hls.Events.MANIFEST_PARSED, () => video.play());\n}`;
        }
        return "";
    };

    const handleCopy = () => {
        navigator.clipboard.writeText(getSnippet());
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <div className="fixed inset-0 z-[100] bg-black/95 backdrop-blur-2xl flex items-center justify-center p-4 xl:p-12 overflow-y-auto">
            <button
                onClick={onClose}
                className="fixed top-8 right-8 z-[110] text-white/40 hover:text-white transition-colors bg-white/5 p-2 rounded-full backdrop-blur-md"
            >
                <X size={24} strokeWidth={2} />
            </button>

            <div className="w-full max-w-7xl grid grid-cols-1 xl:grid-cols-5 gap-8 my-auto">
                {/* Left Side: Video Player */}
                <div ref={containerRef} className="xl:col-span-3 aspect-video relative group ws-card rounded-3xl overflow-hidden shadow-2xl bg-black">
                    <video
                        ref={videoRef}
                        className="w-full h-full object-contain"
                        onTimeUpdate={handleTimeUpdate}
                        onLoadedMetadata={handleLoadedMetadata}
                        onClick={togglePlay}
                    />

                    {/* Controls */}
                    <div className="absolute inset-x-0 bottom-0 p-6 pt-16 bg-gradient-to-t from-black/80 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500">
                        <div className="space-y-4">
                            {/* Seekable progress bar */}
                            <div
                                ref={progressRef}
                                className="h-1 w-full bg-white/10 rounded-full cursor-pointer group/bar"
                                onClick={handleProgressClick}
                            >
                                <div
                                    className="h-full bg-white rounded-full pointer-events-none group-hover/bar:bg-blue-400 transition-colors"
                                    style={{ width: `${progress}%` }}
                                />
                            </div>

                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-5">
                                    <button onClick={togglePlay} className="hover:scale-110 transition-transform text-white">
                                        {isPlaying ? <Pause fill="white" size={20} /> : <Play fill="white" size={20} />}
                                    </button>

                                    {/* Volume */}
                                    <div className="flex items-center gap-2">
                                        <button onClick={toggleMute} className="text-white/70 hover:text-white transition-colors">
                                            {isMuted || volume === 0 ? <VolumeX size={18} /> : <Volume2 size={18} />}
                                        </button>
                                        <div
                                            className="w-16 h-1 bg-white/20 rounded-full cursor-pointer relative"
                                            onClick={handleVolumeClick}
                                        >
                                            <div
                                                className="h-full bg-white rounded-full pointer-events-none"
                                                style={{ width: `${isMuted ? 0 : volume * 100}%` }}
                                            />
                                        </div>
                                    </div>

                                    {/* Time display */}
                                    <span className="text-xs font-mono text-white/50 tabular-nums">
                                        {formatTime(currentTime)} / {formatTime(duration)}
                                    </span>
                                </div>

                                <div className="flex items-center gap-4">
                                    <span className="text-xs font-mono tracking-tighter text-white/30">ABR</span>
                                    <button onClick={handleFullscreen} className="text-white/60 hover:text-white transition-colors">
                                        <Maximize size={18} />
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Right Side: Embed Code Snippets */}
                <div className="xl:col-span-2 flex flex-col ws-card rounded-3xl p-8 border border-white/5 space-y-6 bg-white/[0.02]">
                    <div className="space-y-1">
                        <div className="flex items-center gap-3 text-white">
                            <Code2 size={24} className="text-blue-400" />
                            <h3 className="text-2xl font-bold tracking-tight">Embed this video</h3>
                        </div>
                        <p className="text-muted text-sm ml-9">Stream securely directly into your application.</p>
                    </div>

                    {/* Tabs */}
                    <div className="flex gap-6 border-b border-white/10 pb-0 text-xs font-semibold tracking-widest uppercase">
                        {(["iframe", "react", "hlsjs"] as const).map((t) => (
                            <button
                                key={t}
                                className={`pb-3 px-1 transition-colors relative ${tab === t ? 'text-white' : 'text-muted hover:text-white/70'}`}
                                onClick={() => setTab(t)}
                            >
                                {t === "iframe" ? "IFrame" : t === "react" ? "React" : "HLS.js"}
                                {tab === t && <motion.div layoutId="underline" className="absolute bottom-0 left-0 right-0 h-[2px] bg-blue-400" />}
                            </button>
                        ))}
                    </div>

                    {/* Code Block */}
                    <div className="relative bg-black/40 rounded-2xl p-6 font-mono text-sm overflow-x-auto text-white/80 border border-white/5 flex-grow shadow-inner">
                        <button
                            onClick={handleCopy}
                            className="absolute top-4 right-4 text-xs bg-white/10 hover:bg-white/20 px-3 py-2 rounded-lg transition-colors flex items-center gap-2 text-white"
                        >
                            {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
                            {copied ? "Copied" : "Copy"}
                        </button>
                        <AnimatePresence mode="wait">
                            <motion.pre
                                key={tab}
                                initial={{ opacity: 0, y: 5 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: -5 }}
                                transition={{ duration: 0.15 }}
                                className="pt-8 whitespace-pre-wrap break-all"
                            >
                                <code className="text-[13px] leading-relaxed block text-blue-100/70">
                                    {getSnippet()}
                                </code>
                            </motion.pre>
                        </AnimatePresence>
                    </div>
                </div>
            </div>
        </div>
    );
}
