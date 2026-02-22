"use client";

import { ConnectButton } from "@mysten/dapp-kit";

export default function WalletConnect() {
    return (
        <ConnectButton className="!bg-white !text-black !rounded-full !px-4 !py-2 !text-sm !font-medium hover:!bg-white/90 transition-colors" />
    );
}
