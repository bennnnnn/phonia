import { FlashList } from "@shopify/flash-list";
import { Redirect, useRouter } from "expo-router";
import { useTranslation } from "react-i18next";

import { StateView } from "@/ui/feedback/StateView";
import { SettingsSkeleton } from "@/features/account/components/SettingsSkeleton";
import {
  SettingsGroup,
  SettingsLinkRow,
  SettingsValueRow,
  useSettingsAction,
  useSettingsContentStyle,
} from "@/features/account/components/settingsUi";
import { useAuth } from "@/contexts/AuthContext";
import { useFocusedList } from "@/features/account/hooks/useFocusedList";
import { api, type AuthSession } from "@/lib/api";
import { formatDate } from "@/lib/datetime/format";
import { notifyDestructive } from "@/lib/haptics";
import { useTheme } from "@/lib/theme";

/** "Last active Tue, Oct 21 · 3:04 PM" in the app's own date format; a missing time says so. */
function formatSeen(iso: string | null, t: (key: string, options?: Record<string, unknown>) => string): string {
  const date = iso ? new Date(iso) : null;
  if (!date || Number.isNaN(date.getTime())) return t("settings.last_active_unknown");
  return t("settings.last_active", { when: `${formatDate(date, "weekdayDate")} · ${formatDate(date, "time")}` });
}

async function readSessions(token: string): Promise<AuthSession[]> {
  const data = await api.listSessions(token);
  return data.sessions ?? [];
}

export default function SecuritySettingsScreen() {
  const { token, signOut } = useAuth();
  const { t } = useTranslation();
  const theme = useTheme();
  const contentStyle = useSettingsContentStyle();
  const router = useRouter();
  const action = useSettingsAction();
  const {
    items: sessions,
    setItems: setSessions,
    loading,
    loadError,
    load,
  } = useFocusedList(token, readSessions);

  const revoke = (session: AuthSession) => {
    if (!token || session.current) return;
    void action.run(
      session.id,
      async () => {
        await api.revokeSession(token, session.id);
        notifyDestructive();
        setSessions((rows) => rows.filter((row) => row.id !== session.id));
      },
      {
        confirm: {
          title: t("settings.revoke_session"),
          message: t("settings.revoke_session_confirm"),
          cancelLabel: t("common.cancel"),
          confirmLabel: t("settings.revoke_session"),
          destructive: true,
        },
      },
    );
  };

  const logoutAll = () => {
    if (!token) return;
    void action.run(
      "all",
      async () => {
        await api.logoutAll(token);
        await signOut();
        notifyDestructive();
        router.replace("/login");
      },
      {
        confirm: {
          title: t("settings.sign_out_all"),
          message: t("settings.sign_out_all_confirm"),
          cancelLabel: t("common.cancel"),
          confirmLabel: t("settings.sign_out_all"),
          destructive: true,
        },
      },
    );
  };

  if (!token) return <Redirect href="/login" />;

  return (
    <FlashList
      data={sessions}
      keyExtractor={(session) => session.id}
      style={{ flex: 1, backgroundColor: theme.bg }}
      contentContainerStyle={contentStyle}
      ListEmptyComponent={
        loading && !loadError ? (
          <SettingsSkeleton rows={3} contained accessibilityLabel={t("settings.security")} />
        ) : loadError ? (
          <StateView variant="error" title={t("common.error")} onRetry={() => void load()} />
        ) : null
      }
      renderItem={({ item: session, index }) => (
        <SettingsGroup label={index === 0 ? t("settings.sessions") : undefined}>
          <SettingsValueRow
            title={session.device_label?.trim() || t("settings.unknown_device")}
            subtitle={formatSeen(session.last_seen_at, t)}
            value={session.current ? t("settings.this_device") : undefined}
          />
          {session.current ? null : (
            <SettingsLinkRow
              title={t("settings.revoke_session")}
              danger
              busy={action.busy === session.id}
              disabled={action.busy !== null}
              onPress={() => revoke(session)}
            />
          )}
        </SettingsGroup>
      )}
      ListFooterComponent={
        <SettingsGroup>
          <SettingsLinkRow
            title={t("settings.sign_out_all")}
            danger
            busy={action.busy === "all"}
            disabled={action.busy !== null}
            onPress={logoutAll}
          />
        </SettingsGroup>
      }
    />
  );
}
