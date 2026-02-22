import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
    title: "Walrus Direct | Minimalist Video Platform",
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
                <nav className="fixed top-0 w-full z-50 border-b border-white/5 bg-black/50 backdrop-blur-md">
                    <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <div className="w-6 h-6 bg-white rounded-full" />
                            <span className="font-semibold tracking-tight text-lg">WALRUS DIRECT</span>
                        </div>
                        <div className="flex items-center gap-6 text-sm font-medium text-muted hover:text-foreground transition-colors">
                            <a href="#">Solutions</a>
                            <a href="#">Network</a>
                            <a href="#">Pricing</a>
                            <button className="text-foreground">Connect Wallet</button>
                        </div>
                    </div>
                </nav>
                <main className="pt-16 min-h-screen">
                    {children}
                </main>
                <footer className="border-t border-white/5 py-20 px-6">
                    <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-4 gap-12">
                        <div className="space-y-4">
                            <div className="flex items-center gap-2">
                                <div className="w-5 h-5 bg-white rounded-full" />
                                <span className="font-semibold tracking-tight">WALRUS</span>
                            </div>
                            <p className="text-xs text-muted leading-relaxed">
                                Empowering the next generation of decentralized video infrastructure. Built for developers, scaled by Walrus.
                            </p>
                        </div>
                        <div />
                        <div />
                        <div className="text-right">
                            <p className="text-xs text-muted">© 2026 Walrus Direct. All rights reserved.</p>
                        </div>
                    </div>
                </footer>
            </body>
        </html>
    );
}
