import { useEffect } from "react";
import { useNavigation, useRouter } from "expo-router";
import { useTranslation } from "react-i18next";

import { plainHeaderItems, StackBackButton } from "@/ui/controls/StackBackButton";
import { StateView } from "@/ui/feedback/StateView";
import {
  SettingsGroup,
  SettingsLinkRow,
  SettingsPage,
  SettingsSwitchRow,
  useSettingsAction,
} from "@/features/account/components/settingsUi";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { useAuth } from "@/contexts/AuthContext";
import { getDeviceLocationLabel } from "@/lib/deviceLocation";
import { canUseDeviceLocation } from "@/lib/expoRuntime";
import { useDataControls } from "@/features/account/hooks/useDataControls";
import { accountDeleteFailureKey } from "@/lib/accountDelete";
import { api, withdrawAiDataSharing } from "@/lib/api";
import { ApiRequestError } from "@/lib/api/errorBody";
import { invalidateChatListCache } from "@/features/chat/model/chatListCache";
import { writeCachedUser } from "@/lib/cachedUser";
import { formatDate } from "@/lib/datetime/format";
import { notifyDestructive } from "@/lib/haptics";
import { reportRecoverableError } from "@/lib/reportRecoverableError";
import { shareFailureKey } from "@/lib/shareUnavailable";
import { alertDialog, confirmDialog } from "@/ui/overlay/dialogs";

export default function DataControlsScreen() {
  const { token, user, updateUser, mergeUser } = useAuth();
  const { progress, exportData, cancelExport, deleteAccount } = useDataControls();
  const { t } = useTranslation();
  const feedback = useActionFeedbackOptional();
  const router = useRouter();
  const navigation = useNavigation();
  const action = useSettingsAction();
  const busy = progress !== "idle";

  useEffect(() => {
    const back = busy ? null : <StackBackButton fallback="/settings" />;
    navigation.setOptions({
      gestureEnabled: !busy,
      headerLeft: () => back,
      unstable_headerLeftItems: () => plainHeaderItems(back),
    });
  }, [busy, navigation]);

  const doExport = async () => {
    if (!token || busy) return;
    const ok = await confirmDialog({
      title: t("settings.export_confirm_title"),
      message: t("settings.export_confirm_body"),
      cancelLabel: t("common.cancel"),
      confirmLabel: t("settings.export_confirm"),
    });
    if (!ok) return;
    try {
      await exportData();
    } catch (error) {
      const message = error instanceof Error ? error.message : "";
      if (!message.toLowerCase().includes("cancel")) {
        // A few exports an hour, one at a time: say so rather than "failed".
        const busy = error instanceof ApiRequestError && error.code === "export_busy";
        reportRecoverableError(feedback, t(busy ? "settings.export_busy" : shareFailureKey(error, "settings.export_failed")));
      }
    }
  };

  const confirmDeleteAccount = () => {
    if (!token || busy) return;
    void confirmDialog({
      title: t("delete.title"),
      message: t("delete.message"),
      cancelLabel: t("common.cancel"),
      confirmLabel: t("common.delete"),
      destructive: true,
    }).then(async (ok) => {
      if (!ok) return;
      const outcome = await deleteAccount();
      if (outcome === "deleted") {
        notifyDestructive();
        router.replace("/login");
      } else if (outcome === "failed" || outcome === "unavailable") {
        reportRecoverableError(feedback, t(accountDeleteFailureKey(outcome)));
      }
    });
  };

  // What leaves the phone besides the chat: web searches and the device location.
  const toggleLocation = (enabled: boolean) =>
    void action.run("location", async () => {
      if (!enabled) {
        await updateUser({ location_enabled: false, location: null });
        return;
      }
      if (!canUseDeviceLocation()) {
        void alertDialog({ title: t("common.error"), message: t("settings.location_expo_go") });
        return;
      }
      const label = await getDeviceLocationLabel();
      if (!label) {
        void alertDialog({ title: t("settings.location_denied") });
        return;
      }
      await updateUser({ location_enabled: true, location: label });
    });
  const locationOn = user?.location_enabled === true;

  // Withdrawing stops chat, voice and photo reads on the server at once; the
  // root layout's consent gate then shows what is shared, to agree or sign out.
  const consentAt = typeof user?.ai_data_consent_at === "string" ? user.ai_data_consent_at : null;
  const withdrawConsent = () =>
    void action.run(
      "ai_consent",
      async () => {
        if (!token) return;
        const updated = await withdrawAiDataSharing(token);
        mergeUser(updated);
        void writeCachedUser(updated);
      },
      {
        confirm: {
          title: t("settings.ai_consent_withdraw_title"),
          message: t("settings.ai_consent_withdraw_body"),
          cancelLabel: t("common.cancel"),
          confirmLabel: t("settings.ai_consent_withdraw"),
          destructive: true,
        },
        errorKey: "settings.ai_consent_withdraw_failed",
      },
    );

  const archiveAll = () =>
    void action.run(
      "archive",
      async () => {
        if (!token) return;
        await api.archiveAllChats(token);
        invalidateChatListCache();
      },
      {
        confirm: {
          title: t("settings.archive_all_chats"),
          message: t("settings.archive_all_confirm"),
          cancelLabel: t("common.cancel"),
          confirmLabel: t("settings.archive_all_chats"),
        },
      },
    );

  const deleteAll = () =>
    void action.run(
      "delete",
      async () => {
        if (!token) return;
        await api.deleteAllChats(token);
        notifyDestructive();
        invalidateChatListCache();
      },
      {
        confirm: {
          title: t("settings.delete_all_chats_title"),
          message: t("settings.delete_all_chats_body"),
          cancelLabel: t("common.cancel"),
          confirmLabel: t("settings.delete_all_chats"),
          destructive: true,
        },
      },
    );

  // Deleting signs out mid-way; keep the progress up instead of redirecting.
  if (progress === "deleting") {
    return (
      <StateView
        variant="loading"
        title={t("settings.delete_progress")}
        message={t("settings.delete_progress_body")}
      />
    );
  }

  if (progress === "exporting") {
    return (
      <StateView
        variant="loading"
        title={t("settings.export_progress")}
        message={t("settings.export_progress_body")}
        onRetry={cancelExport}
        retryLabel={t("common.cancel")}
      />
    );
  }

  return (
    <SettingsPage>
      <SettingsGroup>
        <SettingsSwitchRow
          icon="search"
          title={t("settings.web_search")}
          value={user?.web_search_enabled !== false}
          disabled={action.busy !== null}
          busy={action.busy === "web_search"}
          onValueChange={(next) =>
            void action.run("web_search", () => updateUser({ web_search_enabled: next }))
          }
        />
        <SettingsSwitchRow
          icon="map-pin"
          title={t("settings.use_current_location")}
          value={locationOn}
          disabled={action.busy !== null}
          busy={action.busy === "location"}
          onValueChange={toggleLocation}
        />
      </SettingsGroup>
      <SettingsGroup label={t("settings.chats_group")}>
        <SettingsLinkRow
          title={t("settings.archived_chats")}
          href="/settings/archived-chats"
        />
        <SettingsLinkRow
          title={t("settings.archive_all_chats")}
          busy={action.busy === "archive"}
          disabled={action.busy !== null}
          onPress={archiveAll}
        />
        <SettingsLinkRow
          title={t("settings.delete_all_chats")}
          danger
          busy={action.busy === "delete"}
          disabled={action.busy !== null}
          onPress={deleteAll}
        />
      </SettingsGroup>
      <SettingsGroup label={t("settings.your_data")}>
        <SettingsLinkRow title={t("settings.export")} onPress={() => void doExport()} />
        {consentAt ? (
          <SettingsLinkRow
            title={t("settings.ai_consent")}
            value={t("settings.ai_consent_agreed", {
              date: formatDate(new Date(consentAt), "monthDayYear"),
            })}
            accessibilityHint={t("settings.ai_consent_withdraw_hint")}
            busy={action.busy === "ai_consent"}
            disabled={action.busy !== null}
            onPress={withdrawConsent}
          />
        ) : null}
      </SettingsGroup>
      <SettingsGroup label={t("settings.account")}>
        <SettingsLinkRow
          title={t("settings.delete")}
          danger
          onPress={confirmDeleteAccount}
        />
      </SettingsGroup>
    </SettingsPage>
  );
}
