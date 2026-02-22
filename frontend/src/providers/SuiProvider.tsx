"use client";

import { createNetworkConfig, SuiClientProvider, WalletProvider } from '@mysten/dapp-kit';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@mysten/dapp-kit/dist/index.css';

const { networkConfig } = createNetworkConfig({
    localnet: { url: 'http://127.0.0.1:9000', network: 'localnet' as const },
    testnet: { url: 'https://fullnode.testnet.sui.io:443', network: 'testnet' as const },
    mainnet: { url: 'https://fullnode.mainnet.sui.io:443', network: 'mainnet' as const },
});

const queryClient = new QueryClient();

export function SuiProvider({ children }: { children: React.ReactNode }) {
    return (
        <QueryClientProvider client={queryClient}>
            <SuiClientProvider networks={networkConfig} defaultNetwork="testnet">
                <WalletProvider autoConnect>
                    {children}
                </WalletProvider>
            </SuiClientProvider>
        </QueryClientProvider>
    );
}
