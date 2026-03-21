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
                <link rel="preconnect" href="https://fonts.googleapis.com" />
                <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
                <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet" />
            </head>
            <body className="antialiased">
                <SuiProvider>
                    <nav className="fixed top-0 w-full z-50 border-b border-white/5 bg-black/50 backdrop-blur-md">
                        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
                            <div className="flex items-center">
                                <Image src="/logo.jpeg" alt="WalStream" width={120} height={40} className="object-contain" />
                            </div>
                            <div className="flex items-center gap-6 text-sm font-medium text-muted hover:text-foreground transition-colors">
                                <a href="#">Solutions</a>
                                <a href="#">Network</a>
                                <a href="#">Pricing</a>
                                <WalletConnect />
                            </div>
                        </div>
                    </nav>
                    <main className="pt-16 min-h-screen">
                        {children}
                    </main>
                    <footer className="border-t border-white/5 py-20 px-6">
                        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-4 gap-12">
                            <div className="space-y-4">
                                <div className="flex items-center">
                                    <Image src="/logo.jpeg" alt="WalStream" width={100} height={34} className="object-contain" />
                                </div>
                                <p className="text-xs text-muted leading-relaxed">
                                    Developer-first video infrastructure on Sui & Walrus. Upload once, stream anywhere.
                                </p>
                            </div>
                            <div />
                            <div />
                            <div className="text-right">
                                <p className="text-xs text-muted">© 2026 WalStream. All rights reserved.</p>
                            </div>
                        </div>
                    </footer>
                </SuiProvider>
            </body>
        </html>
    );
}
