import { useCallback, useMemo, useState } from "react";
import { StyleSheet, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useTranslation } from "react-i18next";

import { StackBackButton } from "@/ui/controls/StackBackButton";
import { AccountSettingsSection } from "@/features/account/components/AccountSettingsSection";
import { ProfileHeader } from "@/features/account/components/ProfileHeader";
import {
  SettingsGroup,
  SettingsLinkRow,
  SettingsMenuRow,
  SettingsPage,
  useSettingsAction,
} from "@/features/account/components/settingsUi";
import { useAccent, useAppearance } from "@/contexts/AppearanceContext";
import { useAuth } from "@/contexts/AuthContext";
import { useModels } from "@/hooks/useModels";
import { voiceLabel } from "@/features/speech/model/voices";
import { ACCENT_OPTIONS, accentSwatch } from "@/lib/accent";
import { APPEARANCE_OPTIONS } from "@/lib/appearance";
import { LANGUAGES } from "@/lib/i18n/languages";
import { getNotificationPermissionGranted } from "@/features/notifications/model/pushNotifications";
import { Space } from "@/lib/space";
import { useTheme } from "@/lib/theme";

export default function SettingsScreen() {
  const { token, user, signOut, updateUser } = useAuth();
  const { t } = useTranslation();
  const { autoEnabled, modelEnabledSet } = useModels();
  const theme = useTheme();
  const router = useRouter();
  const { preference, setPreference } = useAppearance();
  const { accent, setAccent } = useAccent();
  const action = useSettingsAction();

  const [osPushGranted, setOsPushGranted] = useState<boolean | null>(null);

  // Focus runs on the first visit too, so the OS permission is read once per visit.
  useFocusEffect(
    useCallback(() => {
      if (!token) return;
      void getNotificationPermissionGranted()
        .then(setOsPushGranted)
        .catch(() => setOsPushGranted(false));
    }, [token]),
  );

  const appearanceOptions = useMemo(
    () => APPEARANCE_OPTIONS.map((key) => ({ key, label: t(`settings.appearance_${key}`) })),
    [t],
  );
  const accentOptions = useMemo(
    () =>
      ACCENT_OPTIONS.map((key) => ({
        key,
        label: t(`settings.accent_${key}`),
        swatch: accentSwatch(key, theme.scheme),
      })),
    [t, theme.scheme],
  );
  const languageOptions = useMemo(
    () => LANGUAGES.map((lang) => ({ key: lang.code, label: lang.label })),
    [],
  );
  const language = LANGUAGES.find((lang) => lang.code === user?.locale) ?? LANGUAGES[0];

  const modelsValue = autoEnabled
    ? t("settings.model_auto")
    : t("settings.models_enabled", { count: modelEnabledSet.size });
  const notificationsValue =
    osPushGranted == null
      ? undefined
      : Boolean(user?.push_notifications_enabled) && osPushGranted
        ? t("settings.on")
        : t("settings.off");
  const voiceValue = user?.tts_voice ? voiceLabel(user.tts_voice) : t("settings.voice_default");

  return (
    <SettingsPage underStatusBar>
      <View style={s.profileHeader}>
        <StackBackButton style={s.backButton} />
        <ProfileHeader
          label={t("settings.profile")}
          onPress={() => router.push("/settings/profile")}
        />
      </View>

      <AccountSettingsSection />

      <SettingsGroup label={t("settings.experience")}>
        <SettingsMenuRow
          icon="contrast"
          title={t("settings.appearance")}
          accessibilityHint={t("settings.appearance_summary")}
          value={t(`settings.appearance_${preference}`)}
          options={appearanceOptions}
          selectedKey={preference}
          onSelect={(next) => void setPreference(next)}
        />
        <SettingsMenuRow
          icon="palette"
          title={t("settings.accent")}
          accessibilityHint={t("settings.accent_summary")}
          value={t(`settings.accent_${accent}`)}
          options={accentOptions}
          selectedKey={accent}
          onSelect={(next) => void setAccent(next)}
        />
        <SettingsMenuRow
          icon="languages"
          title={t("settings.language")}
          value={language.label}
          options={languageOptions}
          selectedKey={language.code}
          busy={action.busy === "language"}
          onSelect={(code) => void action.run("language", () => updateUser({ locale: code }))}
        />
      </SettingsGroup>

      <SettingsGroup label={t("settings.assistant")}>
        <SettingsLinkRow
          icon="user-circle"
          title={t("settings.personalization")}
          accessibilityHint={t("settings.personalization_summary")}
          href="/settings/preferences"
        />
        <SettingsLinkRow
          icon="box"
          title={t("settings.memory")}
          accessibilityHint={t("settings.memory_desc")}
          value={user?.memory_enabled ? t("settings.on") : t("settings.off")}
          href="/settings/memory-settings"
        />
        <SettingsLinkRow
          icon="sparkles"
          title={t("settings.model")}
          accessibilityHint={t("settings.model_summary")}
          value={modelsValue}
          href="/settings/models"
        />
        <SettingsLinkRow
          icon="volume"
          title={t("settings.voice")}
          accessibilityHint={t("settings.voice_summary")}
          value={voiceValue}
          href="/settings/voice"
        />
      </SettingsGroup>

      <SettingsGroup>
        <SettingsLinkRow
          icon="bell"
          title={t("settings.notifications")}
          accessibilityHint={t("settings.notifications_summary")}
          value={notificationsValue}
          href="/settings/notifications"
        />
      </SettingsGroup>

      <SettingsGroup label={t("settings.data_and_privacy")}>
        <SettingsLinkRow
          icon="shield"
          title={t("settings.data_controls")}
          accessibilityHint={t("settings.data_controls_summary")}
          value={user?.web_search_enabled === false ? t("settings.web_search_off") : undefined}
          href="/settings/data-controls"
        />
        <SettingsLinkRow
          icon="lock"
          title={t("settings.security")}
          accessibilityHint={t("settings.security_summary")}
          href="/settings/security"
        />
      </SettingsGroup>

      <SettingsGroup>
        <SettingsLinkRow
          icon="help"
          title={t("settings.help")}
          accessibilityHint={t("settings.help_summary")}
          href="/settings/help"
        />
        <SettingsLinkRow
          icon="info"
          title={t("settings.about")}
          accessibilityHint={t("settings.about_summary")}
          href="/settings/about"
        />
      </SettingsGroup>

      <SettingsGroup>
        <SettingsLinkRow
          icon="log-out"
          title={t("settings.sign_out")}
          danger
          busy={action.busy === "sign-out"}
          onPress={() =>
            void action.run(
              "sign-out",
              async () => {
                await signOut();
                router.replace("/login");
              },
              {
                confirm: {
                  title: t("settings.sign_out_confirm_title"),
                  message: t("settings.sign_out_confirm_body"),
                  cancelLabel: t("common.cancel"),
                  confirmLabel: t("settings.sign_out"),
                  destructive: true,
                },
              },
            )
          }
        />
      </SettingsGroup>
    </SettingsPage>
  );
}

const s = StyleSheet.create({
  profileHeader: {
    alignItems: "center",
    paddingBottom: Space.xs,
  },
  backButton: {
    position: "absolute",
    left: 0,
    top: 0,
  },
});
