import { useMemo } from "react";
import { Linking, StyleSheet, Text, View } from "react-native";
import { type TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { useReminderProposal } from "@/features/todos/hooks/useReminderProposal";
import { proposalDueLabel } from "@/features/todos/model/proposalTime";
import {
  proposalAction,
  type ReminderProposal,
  type ReminderProposalAction,
  type ReminderProposalItem,
} from "@/features/todos/model/reminderProposal";
import { repeatMessageKey } from "@/features/todos/model/repeatLabel";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { Button } from "@/ui/controls/Button";
import { Icon } from "@/ui/icons/Icon";
import type { IconName } from "@/ui/icons/names";
import { IconSize } from "@/ui/icons/sizes";

const ICONS: Record<ReminderProposalAction, IconName> = {
  add: "bell",
  complete: "check-circle",
  uncheck: "check",
  delete: "trash",
  set_due: "calendar",
  clear_due: "clock",
  move: "folder",
};

type Props = { proposal: ReminderProposal };

/**
 * "Call mom · Thu, Oct 15, 6:00 PM" and one button. Nothing is saved until it is tapped.
 * The time is the card's zone, named when the phone is in another ("6:00 PM GMT+3").
 */
export function ReminderProposalCard({ proposal }: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const { busy, done, error, alertsOff, confirm } = useReminderProposal(proposal);
  const action = proposalAction(proposal);

  return (
    <View style={s.card} testID="reminder-proposal-card">
      {proposal.items.map((item, index) => {
        const line = detail(item, t, proposal.timeZone);
        return (
          <View key={`${index}:${item.title}`} style={s.item}>
            <Icon name={ICONS[item.action]} size={IconSize.sm} color={theme.textSecondary} />
            <View style={s.itemText}>
              <Text style={[s.title, done && item.action === "delete" && s.removed]}>
                {item.title}
              </Text>
              {line ? <Text style={s.detail}>{line}</Text> : null}
            </View>
          </View>
        );
      })}
      {error ? <Text style={s.error}>{t(`todos.proposal_error_${error}`)}</Text> : null}
      {done ? (
        <View style={s.doneRow} accessibilityLiveRegion="polite">
          <Icon name="check-circle-filled" size={IconSize.sm} color={theme.primary} />
          <Text style={s.doneText}>{t(`todos.proposal_done_${action}`)}</Text>
        </View>
      ) : null}
      {done && alertsOff ? (
        <View style={s.alertsOff}>
          <Text style={s.detail}>{t("todos.alerts_off")}</Text>
          <Button
            title={t("todos.alerts_open_settings")}
            variant="secondary"
            size="sm"
            onPress={() => void Linking.openSettings()}
            style={s.button}
          />
        </View>
      ) : null}
      {done ? null : (
        <Button
          title={t(`todos.proposal_${action}`)}
          variant={action === "delete" ? "destructive" : "primary"}
          size="sm"
          onPress={() => void confirm()}
          loading={busy}
          style={s.button}
        />
      )}
    </View>
  );
}

/** The time in the phone's own language and the card's zone, or the list a move goes to. */
function detail(item: ReminderProposalItem, t: TFunction, timeZone: string | null): string {
  if (item.action === "move" && item.topic) {
    return t("todos.proposal_to_list", { topic: item.topic });
  }
  if (item.action === "clear_due") return t("todos.proposal_no_date");
  const due = item.dueAt ? new Date(item.dueAt) : null;
  if (!due || Number.isNaN(due.getTime())) return item.when ?? "";
  const when = proposalDueLabel(due, timeZone);
  return item.repeat ? `${when} · ${t(repeatMessageKey(item.repeat))}` : when;
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    card: {
      marginTop: Space.sm,
      padding: Space.md,
      gap: Space.sm,
      borderRadius: Radius.menu,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
      backgroundColor: t.bg,
    },
    item: { flexDirection: "row", alignItems: "flex-start", gap: Space.sm },
    itemText: { flex: 1, gap: Space.xxs },
    title: { ...Type.body, ...Weight.semibold, color: t.text },
    removed: { textDecorationLine: "line-through", color: t.textSecondary },
    detail: { ...Type.secondary, color: t.textSecondary },
    error: { ...Type.secondary, color: t.danger },
    button: { alignSelf: "flex-start" },
    doneRow: { flexDirection: "row", alignItems: "center", gap: Space.xs },
    doneText: { ...Type.secondary, ...Weight.semibold, color: t.primary },
    alertsOff: { gap: Space.xs },
  });
}
