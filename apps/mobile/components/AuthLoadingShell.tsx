import { useMemo } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { Button } from "@/ui/controls/Button";
import { confirmDialog } from "@/ui/overlay/dialogs";
import { Space } from "@/lib/space";
import { useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

type Props = {
  failed: boolean;
  onRetry: () => void;
  /** Leaves the account the launch could not restore, as Settings' Sign out does. */
  onSignOut: () => Promise<void>;
};

/**
 * Preserve a recoverable startup failure instead of showing a signed-out app.
 * Retry reads the stored sign-in again; Sign out is the way out when it never
 * comes back (a server that stays unreachable).
 */
export function AuthLoadingShell({ failed, onRetry, onSignOut }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const styles = useMemo(() => StyleSheet.create({
    shell: {
      flex: 1,
      alignItems: "center",
      justifyContent: "center",
      padding: Space.xl,
      gap: Space.md,
      backgroundColor: theme.bg,
    },
    message: { ...Type.body, color: theme.text, textAlign: "center" },
  }), [theme]);
  const signOut = async () => {
    const confirmed = await confirmDialog({
      title: t("settings.sign_out_confirm_title"),
      message: t("settings.sign_out_confirm_body"),
      cancelLabel: t("common.cancel"),
      confirmLabel: t("settings.sign_out"),
      destructive: true,
    });
    if (!confirmed) return;
    await onSignOut().catch(() => {
      console.warn("[auth] could not clear saved credentials");
    });
  };
  return (
    <View style={styles.shell}>
      {failed ? <>
        <Text accessibilityRole="alert" style={styles.message}>{t("login.error_generic")}</Text>
        <Button title={t("common.retry")} onPress={onRetry} />
        <Button title={t("settings.sign_out")} variant="ghost" onPress={() => void signOut()} />
      </> : <ActivityIndicator size="large" color={theme.primary} />}
    </View>
  );
}
