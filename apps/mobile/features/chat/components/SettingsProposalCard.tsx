import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { Icon } from "@/ui/icons/Icon";
import { useTranslation } from "react-i18next";

import { Button } from "@/ui/controls/Button";
import { useSettingsProposal } from "@/features/chat/hooks/useSettingsProposal";
import type { SettingsProposal } from "@/lib/settingsProposal";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { IconSize } from "@/ui/icons/sizes";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";

type Props = {
  proposal: SettingsProposal;
  disabled?: boolean;
};

export function SettingsProposalCard({ proposal, disabled }: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = makeStyles(theme);
  const { busy, done, confirm } = useSettingsProposal(proposal);
  const [error, setError] = useState<string | null>(null);

  const onConfirm = async () => {
    if (busy || done || disabled) return;
    setError(null);
    if (!(await confirm())) {
      setError(t("settings.proposal_failed"));
    }
  };

  return (
    <View style={s.card}>
      <View style={s.header}>
        <Icon name="sliders" size={IconSize.sm} color={theme.primary} />
        <Text style={s.title}>{t("settings.proposal_title")}</Text>
      </View>
      {proposal.changes.map((change) => (
        <Text key={`${change.field}:${change.value}`} style={s.change}>
          {t(`settings.field_${change.field}`, { defaultValue: change.field })} → {change.label}
        </Text>
      ))}
      {error ? <Text style={s.error}>{error}</Text> : null}
      {done ? (
        <View style={s.doneRow}>
          <Icon name="check-circle-filled" size={IconSize.sm} color={theme.primary} />
          <Text style={s.doneText}>{t("settings.proposal_applied")}</Text>
        </View>
      ) : (
        <Button
          title={t("settings.proposal_confirm")}
          onPress={() => void onConfirm()}
          loading={busy}
          disabled={disabled}
          style={s.btn}
        />
      )}
    </View>
  );
}

const makeStyles = (theme: Theme) =>
  StyleSheet.create({
    card: {
      marginTop: Space.sm,
      padding: Space.sm,
      borderRadius: Radius.lg,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
      backgroundColor: theme.surface,
      gap: Space.xs,
    },
    header: { flexDirection: "row", alignItems: "center", gap: Space.xs },
    title: { flex: 1, ...Type.body, ...Weight.bold, color: theme.text },
    change: { ...Type.label, color: theme.textSecondary },
    error: { ...Type.compact, color: theme.danger },
    btn: { marginTop: Space.xxs },
    doneRow: { flexDirection: "row", alignItems: "center", gap: Space.xs, marginTop: Space.xxs },
    doneText: { ...Type.label, color: theme.primary },
  });
