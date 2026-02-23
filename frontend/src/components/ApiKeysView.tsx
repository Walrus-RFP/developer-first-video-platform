"use client";

import React, { useState, useEffect } from "react";
import { Key, Plus, Copy, Check, Trash2 } from "lucide-react";

interface ApiKey {
    key: string;
    name: string;
    created_at: string;
}

interface ApiKeysViewProps {
    address: string;
}

const CONTROL_PLANE = (process.env.NEXT_PUBLIC_CONTROL_PLANE_URL || "http://localhost:8000") + "/v1";

export default function ApiKeysView({ address }: ApiKeysViewProps) {
    const [keys, setKeys] = useState<ApiKey[]>([]);
    const [loading, setLoading] = useState(true);
    const [generating, setGenerating] = useState(false);
    const [copiedKey, setCopiedKey] = useState<string | null>(null);
    const [newKeyName, setNewKeyName] = useState("");
    const [showNewForm, setShowNewForm] = useState(false);

    useEffect(() => {
        fetchKeys();
    }, [address]);

    const fetchKeys = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${CONTROL_PLANE}/api-keys/${address}`);
            if (res.ok) {
                const data = await res.json();
                setKeys(data.api_keys || []);
            }
        } catch (err) {
            console.error("Failed to fetch API keys:", err);
        } finally {
            setLoading(false);
        }
    };

    const generateKey = async () => {
        if (!newKeyName.trim()) return;
        setGenerating(true);
        try {
            const res = await fetch(`${CONTROL_PLANE}/api-keys`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ owner: address, name: newKeyName })
            });
            if (res.ok) {
                setNewKeyName("");
                setShowNewForm(false);
                fetchKeys();
            }
        } catch (err) {
            console.error("Failed to generate key:", err);
        } finally {
            setGenerating(false);
        }
    };

    const copyToClipboard = (text: string) => {
        navigator.clipboard.writeText(text);
        setCopiedKey(text);
        setTimeout(() => setCopiedKey(null), 2000);
    };

    return (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex items-center justify-between border-b border-white/5 pb-6">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">API Keys</h2>
                    <p className="text-muted text-sm mt-1 max-w-xl">
                        Manage the developer keys used to authenticate API requests to the Control Plane for uploading and managing videos.
                    </p>
                </div>
                <button
                    onClick={() => setShowNewForm(true)}
                    className="btn-primary flex items-center gap-2 text-sm px-4 py-2"
                >
                    <Plus size={16} />
                    Generate Key
                </button>
            </div>

            {showNewForm && (
                <div className="glass-card rounded-2xl p-6 border border-white/10 flex items-end gap-4 max-w-xl">
                    <div className="flex-1 space-y-2">
                        <label className="text-xs text-muted uppercase tracking-widest font-semibold">Key Name</label>
                        <input
                            type="text"
                            placeholder="e.g. My Next.js Frontend"
                            value={newKeyName}
                            onChange={(e) => setNewKeyName(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && generateKey()}
                            className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm placeholder:text-muted focus:outline-none focus:border-white/30 transition-colors"
                            autoFocus
                        />
                    </div>
                    <button
                        onClick={generateKey}
                        disabled={generating || !newKeyName.trim()}
                        className="btn-primary px-6 py-2.5 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {generating ? "Generating..." : "Create"}
                    </button>
                    <button
                        onClick={() => setShowNewForm(false)}
                        className="p-2.5 text-muted hover:text-white transition-colors border border-white/5 rounded-xl hover:bg-white/5"
                    >
                        Cancel
                    </button>
                </div>
            )}

            {loading ? (
                <div className="space-y-4">
                    {[1, 2].map(i => (
                        <div key={i} className="h-24 bg-white/5 animate-pulse rounded-2xl" />
                    ))}
                </div>
            ) : keys.length === 0 ? (
                <div className="py-16 text-center border border-dashed border-white/10 rounded-2xl glass-card">
                    <div className="w-16 h-16 bg-white/5 rounded-full flex items-center justify-center mx-auto mb-4">
                        <Key className="text-muted" size={24} />
                    </div>
                    <h3 className="text-xl font-bold mb-2">No API Keys</h3>
                    <p className="text-muted max-w-sm mx-auto mb-6">You haven't generated any API keys yet. Create one to start building.</p>
                    <button onClick={() => setShowNewForm(true)} className="btn-secondary text-sm">
                        Generate First Key
                    </button>
                </div>
            ) : (
                <div className="grid gap-4">
                    {keys.map((keyObj) => (
                        <div key={keyObj.key} className="glass-card rounded-2xl p-6 flex items-center justify-between group border border-transparent hover:border-white/5 transition-colors">
                            <div className="space-y-1">
                                <h3 className="font-semibold">{keyObj.name}</h3>
                                <div className="flex items-center gap-3">
                                    <code className="text-xs text-muted font-mono bg-white/5 px-2 py-1 rounded">
                                        {keyObj.key.substring(0, 8)}...{keyObj.key.substring(keyObj.key.length - 8)}
                                    </code>
                                    <span className="text-xs text-muted">
                                        Created {new Date(keyObj.created_at).toLocaleDateString()}
                                    </span>
                                </div>
                            </div>

                            <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button
                                    onClick={() => copyToClipboard(keyObj.key)}
                                    className="p-2 text-muted hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                                    title="Copy full key"
                                >
                                    {copiedKey === keyObj.key ? <Check size={18} className="text-emerald-400" /> : <Copy size={18} />}
                                </button>
                                {/* We don't have a delete endpoint yet, so this is visual only for now to show intention in UI */}
                                <button
                                    disabled
                                    className="p-2 text-muted/50 rounded-lg cursor-not-allowed"
                                    title="Revoke key (coming soon)"
                                >
                                    <Trash2 size={18} />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
