"use client";

import React, { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import { Play, Pause, Volume2, Maximize, X, Copy, Check, Code2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface VideoPlayerProps {
    videoId: string;
    playbackUrl: string;
    onClose: () => void;
}

export default function VideoPlayer({ videoId, playbackUrl, onClose }: VideoPlayerProps) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [progress, setProgress] = useState(0);
    const [tab, setTab] = useState<"iframe" | "react" | "hlsjs">("iframe");
    const [copied, setCopied] = useState(false);

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
                if (err.name !== "AbortError") {
                    console.error("Playback failed", err);
                }
            }
        };

        if (Hls.isSupported()) {
            const hls = new Hls({
                xhrSetup: (xhr) => {
                    xhr.withCredentials = false;
                }
            });
            hls.loadSource(playbackUrl);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, playVideo);

            hls.on(Hls.Events.ERROR, (event, data) => {
                if (data.fatal) {
                    console.error("HLS Fatal Error:", data.type, data.details, data.error?.message);
                }
            });

            return () => {
                isMounted = false;
                hls.destroy();
            };
        } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
            video.src = playbackUrl;
            video.addEventListener("loadedmetadata", playVideo);
            return () => {
                isMounted = false;
            };
        }
    }, [playbackUrl]);

    const togglePlay = () => {
        if (videoRef.current) {
            if (isPlaying) videoRef.current.pause();
            else videoRef.current.play();
            setIsPlaying(!isPlaying);
        }
    };

    const handleTimeUpdate = () => {
        if (videoRef.current) {
            const p = (videoRef.current.currentTime / videoRef.current.duration) * 100;
            setProgress(p);
        }
    };

    const getSnippet = () => {
        if (tab === "iframe") {
            return `<iframe\n  src="${playbackUrl}"\n  style="width: 100%; aspect-ratio: 16/9; border: none;"\n  allow="autoplay; fullscreen; encrypted-media"\n  allowfullscreen\n></iframe>`;
        }
        if (tab === "react") {
            return `import React from 'react';\n\nexport default function Video() {\n  return (\n    <video \n      src="${playbackUrl}"\n      controls \n      autoPlay \n      className="w-full aspect-video"\n    />\n  );\n}`;
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
                <div className="xl:col-span-3 aspect-video relative group glass-card rounded-3xl overflow-hidden shadow-2xl bg-black">
                    <video
                        ref={videoRef}
                        className="w-full h-full object-contain"
                        onTimeUpdate={handleTimeUpdate}
                        onClick={togglePlay}
                    />

                    {/* Custom Minimal Controls */}
                    <div className="absolute inset-x-0 bottom-0 p-8 pt-20 bg-gradient-to-t from-black/80 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500">
                        <div className="space-y-6">
                            <div className="h-1 w-full bg-white/10 rounded-full overflow-hidden cursor-pointer group/progress">
                                <div
                                    className="h-full bg-white transition-all duration-150"
                                    style={{ width: `${progress}%` }}
                                />
                            </div>

                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-8">
                                    <button onClick={togglePlay} className="hover:scale-110 transition-transform">
                                        {isPlaying ? <Pause fill="white" size={24} /> : <Play fill="white" size={24} />}
                                    </button>
                                    <div className="flex items-center gap-4 opacity-40 hover:opacity-100 transition-opacity">
                                        <Volume2 size={20} />
                                        <div className="w-20 h-1 bg-white/20 rounded-full" />
                                    </div>
                                </div>

                                <div className="flex items-center gap-6 opacity-40">
                                    <span className="text-xs font-mono tracking-tighter">1080P / ABR</span>
                                    <Maximize size={20} className="hover:text-white transition-colors cursor-pointer" />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Right Side: Embed Code Snippets */}
                <div className="xl:col-span-2 flex flex-col glass-card rounded-3xl p-8 border border-white/5 space-y-6 bg-white/[0.02]">
                    <div className="space-y-1">
                        <div className="flex items-center gap-3 text-white">
                            <Code2 size={24} className="text-blue-400" />
                            <h3 className="text-2xl font-bold tracking-tight">Embed this video</h3>
                        </div>
                        <p className="text-muted text-sm ml-9">Stream securely directly into your application.</p>
                    </div>

                    {/* Tabs */}
                    <div className="flex gap-6 border-b border-white/10 pb-0 text-xs font-semibold tracking-widest uppercase">
                        <button
                            className={`pb-3 px-1 transition-colors relative ${tab === 'iframe' ? 'text-white' : 'text-muted hover:text-white/70'}`}
                            onClick={() => setTab('iframe')}
                        >
                            IFrame
                            {tab === 'iframe' && <motion.div layoutId="underline" className="absolute bottom-0 left-0 right-0 h-[2px] bg-blue-400" />}
                        </button>
                        <button
                            className={`pb-3 px-1 transition-colors relative ${tab === 'react' ? 'text-white' : 'text-muted hover:text-white/70'}`}
                            onClick={() => setTab('react')}
                        >
                            React Component
                            {tab === 'react' && <motion.div layoutId="underline" className="absolute bottom-0 left-0 right-0 h-[2px] bg-blue-400" />}
                        </button>
                        <button
                            className={`pb-3 px-1 transition-colors relative ${tab === 'hlsjs' ? 'text-white' : 'text-muted hover:text-white/70'}`}
                            onClick={() => setTab('hlsjs')}
                        >
                            Core HLS.js
                            {tab === 'hlsjs' && <motion.div layoutId="underline" className="absolute bottom-0 left-0 right-0 h-[2px] bg-blue-400" />}
                        </button>
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
                                className="pt-8 whitespace-pre-wrap word-break-all"
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
