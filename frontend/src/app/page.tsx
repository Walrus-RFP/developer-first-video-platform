"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useRouter } from "next/navigation";
import UploadModal from "@/components/UploadModal";

export default function Home() {
    const [showUpload, setShowUpload] = useState(false);
    const router = useRouter();

    return (
        <div className="max-w-7xl mx-auto px-6">
            {/* Hero Section */}
            <section
                className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center min-h-[80vh] py-20 pt-28 relative"
                style={{
                    backgroundImage: "radial-gradient(circle, #1e1e1e 1px, transparent 1px)",
                    backgroundSize: "28px 28px",
                    maskImage: "radial-gradient(ellipse 80% 70% at 50% 50%, black 60%, transparent 100%)",
                }}
            >
                <motion.div
                    initial={{ opacity: 0, y: 24 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.7 }}
                    className="space-y-7"
                >
                    <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-white/10 text-[10px] font-semibold tracking-widest text-muted uppercase">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#2D9448]" />
                        Live on Sui Testnet
                    </div>
                    <div className="font-display leading-[0.9] space-y-0">
                        <div style={{ fontSize: "clamp(3.8rem, 8vw, 7rem)", color: "#E8372C" }}>UPLOAD.</div>
                        <div style={{ fontSize: "clamp(3.8rem, 8vw, 7rem)", color: "#F5C518" }}>STREAM.</div>
                        <div style={{ fontSize: "clamp(3.8rem, 8vw, 7rem)", color: "#2D9448" }}>OWN.</div>
                    </div>
                    <p className="text-base max-w-[44ch] leading-[1.7] font-light" style={{ color: "#888" }}>
                        Decentralized video infrastructure on Sui & Walrus, with on-chain access control, threshold encryption, and a developer-first REST API.
                    </p>
                    <div className="flex gap-3">
                        <button onClick={() => setShowUpload(true)} className="btn-primary flex items-center gap-2">
                            <Plus size={16} /> Upload Video
                        </button>
                        <button onClick={() => router.push("/dashboard")} className="btn-secondary">
                            Open Dashboard
                        </button>
                    </div>
                </motion.div>

                {/* Code block */}
                <motion.div
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.7, delay: 0.2 }}
                    className="ws-card rounded-2xl overflow-hidden hidden lg:block self-center"
                >
                    <div className="flex items-center gap-1.5 px-4 py-3 border-b border-white/5">
                        <span className="w-2.5 h-2.5 rounded-full bg-[#E8372C]" />
                        <span className="w-2.5 h-2.5 rounded-full bg-[#F5C518]" />
                        <span className="w-2.5 h-2.5 rounded-full bg-[#2D9448]" />
                        <span className="ml-3 text-[11px] text-muted font-mono">walstream.ts</span>
                    </div>
                    <div className="p-6 text-[12.5px] leading-[1.75] font-mono overflow-x-auto space-y-0">
                        <div><span style={{color:"#888"}}>import</span>{" { "}<span style={{color:"#2E5CE6"}}>WalStream</span>{" } "}<span style={{color:"#888"}}>from</span>{" "}<span style={{color:"#2D9448"}}>&apos;@walstream/sdk&apos;</span></div>
                        <div>&nbsp;</div>
                        <div><span style={{color:"#888"}}>const</span>{" client = "}<span style={{color:"#888"}}>new</span>{" "}<span style={{color:"#2E5CE6"}}>WalStream</span>{"({"}</div>
                        <div>&nbsp;&nbsp;<span style={{color:"#aaa"}}>apiKey</span>{": "}<span style={{color:"#F5C518"}}>&quot;ws_live_••••••••&quot;</span></div>
                        <div>{"});"}</div>
                        <div>&nbsp;</div>
                        <div><span style={{color:"#444"}}>{"//"} Upload &amp; store on Walrus forever</span></div>
                        <div><span style={{color:"#888"}}>const</span>{" video = "}<span style={{color:"#888"}}>await</span>{" client."}<span style={{color:"#E8372C"}}>upload</span>{"(file, {"}</div>
                        <div>&nbsp;&nbsp;<span style={{color:"#aaa"}}>title</span>{": "}<span style={{color:"#2D9448"}}>&quot;My Video&quot;</span>{","}</div>
                        <div>&nbsp;&nbsp;<span style={{color:"#aaa"}}>isPublic</span>{": "}<span style={{color:"#F5C518"}}>true</span></div>
                        <div>{"});"}</div>
                        <div>&nbsp;</div>
                        <div><span style={{color:"#444"}}>{"//"} video.walrus_blob_id &nbsp;→ &quot;BNi4xW...&quot;</span></div>
                        <div><span style={{color:"#444"}}>{"//"} video.sui_object_id &nbsp;&nbsp;→ &quot;0x1a2b...&quot;</span></div>
                        <div><span style={{color:"#444"}}>{"//"} video.playback_url &nbsp;&nbsp;→ signed HLS URL</span></div>
                    </div>
                </motion.div>
            </section>

            <AnimatePresence>
                {showUpload && (
                    <UploadModal
                        onClose={() => setShowUpload(false)}
                        onSuccess={() => router.push("/dashboard")}
                    />
                )}
            </AnimatePresence>
        </div>
    );
}
