import { useTranslation } from "react-i18next";

import {
  SettingsGroup,
  SettingsLinkRow,
  SettingsPage,
  SettingsValueRow,
} from "@/features/account/components/settingsUi";
import { useAuth } from "@/contexts/AuthContext";
import { useLiveTalkMinutes } from "@/features/account/hooks/useLiveTalkMinutes";
import { useUsage } from "@/features/account/hooks/useUsage";
import { hasPlanFeature } from "@/lib/plan";
import { formatUsageSummary } from "@/lib/quota";

/** Settings → Usage: today's share of the limit and this month's live talk minutes. */
export default function UsageScreen() {
  const { user } = useAuth();
  const { t } = useTranslation();
  const { usage, loading, error, refresh } = useUsage();
  const isPaid = hasPlanFeature(user, "all_models");
  const liveTalk = useLiveTalkMinutes(hasPlanFeature(user, "live_talk"));

  return (
    <SettingsPage>
      <SettingsGroup>
        {/* Never a blank row: today's share, "…" while it loads, or a retry. */}
        {usage || !error ? (
          <SettingsValueRow
            title={t("settings.usage_today")}
            value={usage ? formatUsageSummary(usage, isPaid, t) : loading ? "…" : undefined}
          />
        ) : (
          <SettingsLinkRow
            title={t("settings.usage_today")}
            value={t("settings.usage_unavailable")}
            onPress={() => void refresh({ force: true })}
          />
        )}
        {liveTalk ? (
          <SettingsValueRow
            title={t("settings.live_talk_minutes")}
            value={t("settings.live_talk_minutes_left", {
              count: liveTalk.remaining,
              limit: liveTalk.limit,
            })}
          />
        ) : null}
      </SettingsGroup>
    </SettingsPage>
  );
}
