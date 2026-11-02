import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "expo-router";
import { useTranslation } from "react-i18next";

import {
  SettingsGroup,
  SettingsLinkRow,
  SettingsPage,
  SettingsSwitchRow,
} from "@/features/account/components/settingsUi";
import { useAuth } from "@/contexts/AuthContext";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { StateView } from "@/ui/feedback/StateView";
import { useAccountViewOwner } from "@/hooks/useAccountViewOwner";
import { useReconnectRefresh } from "@/hooks/useReconnectRefresh";
import { useMemoryToggle } from "@/features/memory/hooks/useMemoryToggle";
import {
  fetchMemories,
  getCachedMemories,
  memoriesReadAt,
  prefetchMemories,
  subscribeMemoriesCache,
} from "@/features/memory/model/memoryListCache";
import { reportRecoverableError } from "@/lib/reportRecoverableError";

export default function MemorySettingsScreen() {
  const view = useAccountViewOwner();
  return <MemorySettingsContent key={view.key} isCurrentView={view.isCurrent} />;
}

function MemorySettingsContent({ isCurrentView }: { isCurrentView: () => boolean }) {
  const { token, user, updateUser } = useAuth();
  const { t } = useTranslation();
  const router = useRouter();
  const [memCount, setMemCount] = useState(0);
  const [loadError, setLoadError] = useState(false);
  const requestRef = useRef(0);
  const feedback = useActionFeedbackOptional();
  const { saving, toggle } = useMemoryToggle(isCurrentView, useCallback(() => {
    reportRecoverableError(feedback, t("common.error"));
  }, [feedback, t]));

  const onError = useCallback(() => {
    reportRecoverableError(feedback, t("common.error"));
  }, [feedback, t]);

  const loadMemories = useCallback(async (force = false) => {
    if (!token || !isCurrentView()) return;
    const request = ++requestRef.current;
    setLoadError(false);
    const result = await fetchMemories(token, { force });
    if (!isCurrentView() || request !== requestRef.current) return;
    if (result.error) setLoadError(true);
    else setMemCount((getCachedMemories() ?? result.data).length);
  }, [token, isCurrentView]);

  useEffect(() => subscribeMemoriesCache(() => {
    if (isCurrentView()) setMemCount(getCachedMemories()?.length ?? 0);
  }), [isCurrentView]);

  useEffect(() => {
    void loadMemories();
  }, [loadMemories]);
  // The API back after an outage: the count read again while the page has focus, unless a read
  // landed since the connection was lost.
  useReconnectRefresh(() => void loadMemories(), { onScreen: isCurrentView, readAt: memoriesReadAt });

  const toggleSensitive = useCallback((enabled: boolean) => {
    if (!isCurrentView() || saving) return;
    void updateUser({ memory_include_sensitive: enabled }).catch(onError);
  }, [isCurrentView, saving, updateUser, onError]);

  return (
    <SettingsPage>
      <SettingsGroup>
        <SettingsSwitchRow
          icon="box"
          title={t("settings.memory")}
          subtitle={t("settings.memory_desc")}
          value={user?.memory_enabled ?? true}
          disabled={saving}
          busy={saving}
          onValueChange={toggle}
        />
        <SettingsSwitchRow
          icon="shield"
          title={t("settings.memory_include_sensitive")}
          subtitle={t("settings.memory_include_sensitive_desc")}
          value={user?.memory_include_sensitive ?? false}
          disabled={saving}
          onValueChange={toggleSensitive}
        />
        <SettingsLinkRow
          icon="book"
          title={t("settings.memory_view")}
          value={
            memCount > 0
              ? t("settings.memory_count", { count: memCount })
              : undefined
          }
          chevron
          onPress={() => {
            if (!isCurrentView()) return;
            if (token) prefetchMemories(token);
            router.push("/memory");
          }}
        />
      </SettingsGroup>
      {loadError ? <StateView
        variant="error"
        title={t("common.error")}
        onRetry={() => void loadMemories(true)}
        retryLabel={t("common.retry")}
      /> : null}
    </SettingsPage>
  );
}
