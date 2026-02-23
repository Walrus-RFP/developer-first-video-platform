"use client";

import React, { useState } from "react";
import { X, Upload, Check, Loader2, AlertCircle } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useCurrentAccount, useSignAndExecuteTransaction, useSuiClient } from "@mysten/dapp-kit";
import { Transaction } from "@mysten/sui/transactions";

const CONTROL_PLANE = (process.env.NEXT_PUBLIC_CONTROL_PLANE_URL || "http://127.0.0.1:8000") + "/v1";
const DATA_PLANE = (process.env.NEXT_PUBLIC_DATA_PLANE_URL || "http://127.0.0.1:8001") + "/v1";
const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB chunks

export default function UploadModal({ onClose, onSuccess }: { onClose: () => void, onSuccess: () => void }) {
    const [file, setFile] = useState<File | null>(null);
    const [title, setTitle] = useState("");
    const [apiKey, setApiKey] = useState("");
    const [isPublic, setIsPublic] = useState(true);
    const [status, setStatus] = useState<"idle" | "uploading" | "processing" | "success" | "error">("idle");
    const [progress, setProgress] = useState(0);
    const [statusMsg, setStatusMsg] = useState("");
    const [error, setError] = useState("");
    const account = useCurrentAccount();
    const { mutateAsync: signAndExecuteTransaction } = useSignAndExecuteTransaction();
    const suiClient = useSuiClient();

    const handleUpload = async () => {
        if (!file) return;
        setStatus("uploading");
        setProgress(0);

        try {
            // 1. Create session (requires API Key)
            const sessResp = await fetch(`${CONTROL_PLANE}/upload-session`, {
                method: "POST",
                headers: { "X-API-Key": apiKey }
            });

            if (!sessResp.ok) {
                if (sessResp.status === 401 || sessResp.status === 403) throw new Error("Invalid API Key");
                throw new Error("Failed to create upload session");
            }

            const sessData = await sessResp.json();
            const sessionId = sessData.upload_session_id;

            const totalChunks = Math.ceil(file.size / CHUNK_SIZE);

            // We are forcing a fresh upload every time to bypass any corrupt cached blobs
            // on the backend from previous failed attempts.
            for (let i = 0; i < totalChunks; i++) {


                const start = i * CHUNK_SIZE;
                const end = Math.min(file.size, start + CHUNK_SIZE);
                const chunk = file.slice(start, end);

                const formData = new FormData();
                formData.append("file", chunk, `chunk_${i}`);

                const chunkResp = await fetch(`${DATA_PLANE}/upload-chunk/${sessionId}/chunk_${i}/${i}`, {
                    method: "POST",
                    body: formData
                });

                if (!chunkResp.ok) {
                    const errText = await chunkResp.text();
                    console.error(`Chunk ${i} upload failed:`, errText);
                    throw new Error(`Chunk ${i} upload failed: ${errText}`);
                }

                setProgress(Math.round(((i + 1) / totalChunks) * 100));

            }

            // 3. Kick off async completion
            setStatus("processing");
            setStatusMsg("Starting processing job...");
            const params = new URLSearchParams();
            if (account) params.set("owner", account.address);
            if (title.trim()) params.set("title", title.trim());
            params.set("is_public", isPublic ? "true" : "false");

            const qs = params.toString() ? `?${params.toString()}` : "";
            const completeResp = await fetch(`${CONTROL_PLANE}/complete-upload/${sessionId}${qs}`, {
                method: "POST",
                headers: { "X-API-Key": apiKey }
            });

            if (!completeResp.ok) {
                const errorData = await completeResp.json().catch(() => ({ detail: "Upload completion failed" }));
                throw new Error(errorData.detail || "Upload completion failed");
            }

            // 4. Poll for status
            let completeData = null;
            while (true) {
                await new Promise(resolve => setTimeout(resolve, 3000));

                const statusResp = await fetch(`${CONTROL_PLANE}/upload-status/${sessionId}`);
                if (!statusResp.ok) continue;

                const statusData = await statusResp.json();

                if (statusData.status === "failed") {
                    throw new Error(statusData.error || "Async upload processing failed on backend.");
                } else if (statusData.status === "upload completed") {
                    completeData = statusData;
                    break;
                } else {
                    setStatusMsg(statusData.status);
                }
            }

            // 5. Sign and execute on-chain transaction
            setStatusMsg("Requesting Wallet Signature...");
            if (account && completeData.sui_package_id && completeData.sui_registry_id) {
                const tx = new Transaction();
                tx.moveCall({
                    target: `${completeData.sui_package_id}::video_registry::register_video`,
                    arguments: [
                        tx.object(completeData.sui_registry_id),
                        tx.pure.string(completeData.video_id)
                    ]
                });

                signAndExecuteTransaction(
                    { transaction: tx },
                    {
                        onSuccess: (txRes) => {
                            setStatus("processing"); // keep processing while waiting for chain

                            // Wait for the transaction to actually be processed on the chain
                            suiClient.waitForTransaction({
                                digest: txRes.digest,
                                options: { showEffects: true }
                            }).then((txResult) => {
                                console.log("Transaction finalized on-chain:", txResult);
                                setStatus("success");
                                setTimeout(() => {
                                    onSuccess();
                                    onClose();
                                }, 2000);
                            }).catch(err => {
                                console.error("Error waiting for tx:", err);
                                setError("Transaction signed but validation timed out.");
                                setStatus("error");
                            });
                        },
                        onError: (e) => {
                            console.error("Wallet transaction failed:", e);
                            setError("Wallet transaction rejected or failed.");
                            setStatus("error");
                        }
                    }
                );
            } else {
                setStatus("success");
                setTimeout(() => {
                    onSuccess();
                    onClose();
                }, 2000);
            }

        } catch (err: any) {
            console.error("Upload error:", err);
            setError(err.message || "Upload failed. Please check backend connectivity.");
            setStatus("error");
        }
    };

    return (
        <div className="fixed inset-0 z-[100] bg-black/80 backdrop-blur-md flex items-center justify-center p-6">
            <motion.div
                initial={{ scale: 0.95, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                className="w-full max-w-xl glass-card rounded-3xl p-10 relative overflow-hidden"
            >
                <button onClick={onClose} className="absolute top-6 right-6 text-muted hover:text-white transition-colors">
                    <X size={24} />
                </button>

                <div className="space-y-8">
                    <div className="space-y-2">
                        <h2 className="text-3xl font-bold tracking-tight">ENLIST ASSET.</h2>
                        <p className="text-muted text-sm">Upload your video to the Walrus decentralized network.</p>
                    </div>

                    {status === "idle" && (
                        <div className="space-y-4">
                            <div className="flex gap-4">
                                <input
                                    type="text"
                                    placeholder="API Key (required)"
                                    value={apiKey}
                                    onChange={(e) => setApiKey(e.target.value)}
                                    className="w-1/2 bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm placeholder:text-muted focus:outline-none focus:border-white/30 transition-colors"
                                />
                                <input
                                    type="text"
                                    placeholder="Video title (optional)"
                                    value={title}
                                    onChange={(e) => setTitle(e.target.value)}
                                    className="w-1/2 bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm placeholder:text-muted focus:outline-none focus:border-white/30 transition-colors"
                                />
                            </div>
                            <div
                                className="border-2 border-dashed border-white/10 rounded-2xl p-12 text-center space-y-4 hover:border-white/20 transition-colors cursor-pointer group"
                                onClick={() => document.getElementById("fileInput")?.click()}
                            >
                                <input
                                    id="fileInput"
                                    type="file"
                                    className="hidden"
                                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                                />
                                <div className="w-16 h-16 bg-white/5 rounded-full flex items-center justify-center mx-auto group-hover:scale-110 transition-transform">
                                    <Upload size={28} className="text-muted group-hover:text-white transition-colors" />
                                </div>
                                <div className="space-y-1">
                                    <p className="font-medium">{file ? file.name : "Choose File"}</p>
                                    <p className="text-xs text-muted">MP4, MOV up to 2GB</p>
                                </div>
                            </div>

                            <div className="flex bg-white/5 border border-white/10 rounded-xl p-1 overflow-hidden">
                                <button
                                    onClick={() => setIsPublic(true)}
                                    className={`flex-1 py-2 text-sm font-medium rounded-lg transition-colors ${isPublic ? "bg-white text-black" : "text-muted hover:text-white"}`}
                                >
                                    Public (Free)
                                </button>
                                <button
                                    onClick={() => setIsPublic(false)}
                                    className={`flex-1 py-2 text-sm font-medium rounded-lg transition-colors ${!isPublic ? "bg-white text-black" : "text-muted hover:text-white"}`}
                                >
                                    Private (SEAL)
                                </button>
                            </div>
                        </div>
                    )}

                    {(status === "uploading" || status === "processing") && (
                        <div className="space-y-6 py-10">
                            <div className="flex justify-between text-sm font-medium">
                                <span className="flex items-center gap-2">
                                    <Loader2 className="animate-spin" size={16} />
                                    {status === "uploading" ? `CARRYING BLOCKS... ${progress}%` : (statusMsg || "RECONSTITUTING AT WALRUS...")}
                                </span>
                                <span className="text-muted">{file?.name}</span>
                            </div>
                            <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
                                <motion.div
                                    className="h-full bg-white rounded-full bg-glow"
                                    initial={{ width: 0 }}
                                    animate={{ width: `${progress}%` }}
                                    transition={{ duration: 0.3 }}
                                />
                            </div>
                        </div>
                    )}

                    {status === "success" && (
                        <div className="py-10 text-center space-y-4">
                            <div className="w-20 h-20 bg-white rounded-full flex items-center justify-center mx-auto">
                                <Check size={40} className="text-black" />
                            </div>
                            <p className="font-bold text-xl tracking-tight">MISSION SUCCESS.</p>
                        </div>
                    )}

                    {status === "error" && (
                        <div className="py-10 text-center space-y-4 text-red-400">
                            <AlertCircle size={40} className="mx-auto" />
                            <p className="text-sm font-medium">{error}</p>
                            <button onClick={() => setStatus("idle")} className="text-xs underline text-muted">Try again</button>
                        </div>
                    )}

                    <div className="flex gap-4">
                        <button
                            disabled={!file || !apiKey || status !== "idle"}
                            onClick={handleUpload}
                            className="btn-primary flex-1 disabled:opacity-20 flex justify-center items-center gap-2 transition-all hover:scale-105"
                        >
                            Confirm Upload
                        </button>
                        <button onClick={onClose} className="btn-secondary">Cancel</button>
                    </div>
                </div>
            </motion.div >
        </div >
    );
}
