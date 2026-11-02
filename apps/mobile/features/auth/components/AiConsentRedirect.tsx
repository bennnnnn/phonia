import { useEffect } from "react";
import { usePathname, useRootNavigationState, useRouter } from "expo-router";

import { useAuthOptional } from "@/contexts/AuthContext";
import { aiConsentRedirect } from "@/features/auth/model/aiConsent";

/**
 * Mounted once in the root layout: sends a signed-in account that has not agreed to
 * the outside-AI disclosure (one from before sign-in recorded it, or one that withdrew)
 * to /consent from whichever screen it opened on, and keeps it there until it agrees
 * or signs out. The routes themselves stay thin.
 */
export function AiConsentRedirect() {
  const router = useRouter();
  const pathname = usePathname();
  // router.replace throws until the root navigator has mounted.
  const navigationReady = Boolean(useRootNavigationState()?.key);
  const target = aiConsentRedirect(useAuthOptional()?.user ?? null, pathname);

  useEffect(() => {
    if (navigationReady && target) router.replace(target);
  }, [navigationReady, router, target]);

  return null;
}
