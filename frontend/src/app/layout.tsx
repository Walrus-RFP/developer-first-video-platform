import type { Metadata } from "next";
import "./globals.css";
import Image from "next/image";
import { SuiProvider } from "@/providers/SuiProvider";
import WalletConnect from "@/components/WalletConnect";

export const metadata: Metadata = {
    title: "WalStream | Developer-First Video Infrastructure",
    description: "Next-generation video infrastructure on Sui & Walrus",
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en">
            <head>
                <link rel="icon" href="/logo.jpeg" />
                <link rel="preconnect" href="https://fonts.googleapis.com" />
                <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
                <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
            </head>
            <body className="antialiased">
                <SuiProvider>
                    <nav className="fixed top-0 w-full z-50 bg-black/50 backdrop-blur-md" style={{ borderBottom: "1px solid #1c1c1c" }}>
                        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
                            <a href="/">
                                <Image src="/logo.jpeg" alt="WalStream" width={74} height={74} className="object-contain rounded-md" />
                            </a>
                            <div className="flex items-center gap-6">
                                <a href="/" className="text-sm text-muted hover:text-white transition-colors tracking-wide">Home</a>
                                <a href="/dashboard" className="text-sm text-muted hover:text-white transition-colors tracking-wide">Dashboard</a>
                                <WalletConnect />
                            </div>
                        </div>
                    </nav>
                    <main className="pt-16 min-h-screen">
                        {children}
                    </main>
                    <footer className="border-t border-white/5 py-10 px-6">
                        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
                            <div className="flex items-center gap-4">
                                <Image src="/logo.jpeg" alt="WalStream" width={36} height={36} className="object-contain rounded-md" />
                                <div>
                                    <p className="text-sm font-semibold">WalStream</p>
                                    <p className="text-xs text-muted">Developer-first video infrastructure on Sui & Walrus</p>
                                </div>
                            </div>
                            <div className="flex items-center gap-6">
                                <p className="text-[10px] tracking-[0.25em] font-bold">
                                    <span style={{ color: "#E8372C" }}>UPLOAD</span> · <span style={{ color: "#F5C518" }}>STREAM</span> · <span style={{ color: "#2D9448" }}>OWN</span>
                                </p>
                                <p className="text-xs text-muted">© 2026 WalStream</p>
                            </div>
                        </div>
                    </footer>
                </SuiProvider>
            </body>
        </html>
    );
}
