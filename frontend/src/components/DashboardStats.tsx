"use client";

import React, { useEffect, useState } from "react";
import { HardDrive, PlayCircle, Activity, Globe } from "lucide-react";
import { motion } from "framer-motion";

const API_BASE = (process.env.NEXT_PUBLIC_CONTROL_PLANE_URL || "http://127.0.0.1:8000") + "/v1";

export default function DashboardStats() {
    const [stats, setStats] = useState<any>(null);

    const fetchStats = async () => {
        try {
            const res = await fetch(`${API_BASE}/metrics`);
            const data = await res.json();
            setStats(data);
        } catch (err) {
            console.error("Failed to fetch stats", err);
        }
    };

    useEffect(() => {
        let isMounted = true;

        const getData = async () => {
            if (isMounted) await fetchStats();
        };

        getData();
        const interval = setInterval(getData, 15000);

        return () => {
            isMounted = false;
            clearInterval(interval);
        };
    }, []);

    if (!stats) return null;

    const { metrics } = stats;

    const formatSize = (bytes: number) => {
        if (bytes === 0) return "0 B";
        const k = 1024;
        const sizes = ["B", "KB", "MB", "GB", "TB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
    };

    const statItems = [
        { label: "ASSETS STORED", value: metrics.total_videos, icon: PlayCircle },
        { label: "WALRUS CAPACITY", value: formatSize(metrics.total_storage_bytes), icon: HardDrive },
        { label: "READ VOLUME", value: formatSize(metrics.bandwidth?.egress_total || 0), icon: Globe },
        { label: "INGRESS (LIFETIME)", value: formatSize(metrics.bandwidth?.ingress_total || 0), icon: Activity },
    ];

    return (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {statItems.map((item, i) => (
                <motion.div
                    key={item.label}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.1 }}
                    className="glass-card p-6 rounded-2xl space-y-3"
                >
                    <div className="flex items-center gap-2 text-muted">
                        <item.icon size={14} className="opacity-50" />
                        <span className="text-[10px] tracking-widest font-bold uppercase">{item.label}</span>
                    </div>
                    <div className="text-2xl font-bold tracking-tight">{item.value}</div>
                </motion.div>
            ))}
        </div>
    );
}
