import { createContext, useContext, type ReactNode } from "react";

import { useNetworkStatus } from "@/hooks/useNetworkStatus";
import type { ConnectivityStatus } from "@/lib/networkProbe";

type NetworkContextValue = { isOffline: boolean; status: ConnectivityStatus };

const NetworkContext = createContext<NetworkContextValue | null>(null);

export function NetworkProvider({ children }: { children: ReactNode }) {
  const value = useNetworkStatus();
  return <NetworkContext.Provider value={value}>{children}</NetworkContext.Provider>;
}

export function useNetwork(): NetworkContextValue {
  const ctx = useContext(NetworkContext);
  // Fall back to "online" if used outside the provider rather than crashing screens.
  return ctx ?? { isOffline: false, status: "online" };
}
