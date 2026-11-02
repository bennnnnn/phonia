import type { ModelInfo } from "@/lib/api";

/** The model list before the first /models response on a fresh install (no
 * cached catalog yet): the one model the composer needs to send. The server
 * owns the catalog, its prices and its quota multipliers; the phone keeps no
 * copy of them. */
export const MODEL_CATALOG_FALLBACK: ModelInfo[] = [
  {
    id: "free-chat",
    label: "Claude Haiku 5.5",
    tier: "fast",
    plan_access: "free",
    description: "Fast everyday chat — cheap and capable.",
    available: true,
  },
];
