import type { Usage } from "@/lib/api";

export function usageUsedTokens(usage: Usage): number {
  if (usage.used_tokens != null) return usage.used_tokens;
  return Math.max(0, usage.daily_limit - usage.remaining);
}

export function usageUsedPercent(usage: Usage): number {
  if (usage.daily_limit <= 0) return 0;
  return Math.min(100, (usageUsedTokens(usage) / usage.daily_limit) * 100);
}

export function usageRemainingPercent(usage: Usage): number {
  if (usage.daily_limit <= 0) return 0;
  return Math.max(0, Math.min(100, (usage.remaining / usage.daily_limit) * 100));
}

export function formatUsageSummary(
  usage: Usage,
  isPaid: boolean,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  if (usage.remaining <= 0) {
    return isPaid ? t("settings.usage_exhausted_paid") : t("settings.usage_exhausted");
  }
  const pct = Math.round(usageRemainingPercent(usage));
  return isPaid ? t("settings.usage_left_paid", { pct }) : t("settings.usage_left", { pct });
}
