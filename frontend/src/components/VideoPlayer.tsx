"use client";

import React, { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import { Play, Pause, Volume2, Maximize, X } from "lucide-react";

interface VideoPlayerProps {
    videoId: string;
    playbackUrl: string;
    onClose: () => void;
}

export default function VideoPlayer({ videoId, playbackUrl, onClose }: VideoPlayerProps) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [progress, setProgress] = useState(0);

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

    return (
        <div className="fixed inset-0 z-[100] bg-black/95 backdrop-blur-2xl flex items-center justify-center p-4 md:p-12">
            <button
                onClick={onClose}
                className="absolute top-8 right-8 text-white/40 hover:text-white transition-colors"
            >
                <X size={32} strokeWidth={1} />
            </button>

            <div className="w-full max-w-5xl aspect-video relative group glass-card rounded-3xl overflow-hidden shadow-2xl">
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
        </div>
    );
}
