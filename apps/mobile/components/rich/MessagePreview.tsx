import { useMemo } from "react";
import { StyleSheet, Text } from "react-native";
import { useTranslation } from "react-i18next";

import { CopyButton } from "@/components/CopyButton";
import { CardShell } from "@/components/rich/CardShell";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

type Props = { text: string; label?: string };

export function MessagePreview({ text, label }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const resolvedLabel = label ?? t("rich.message_draft");
  // Preserve explicitly requested template slots. The prompt prevents
  // invented placeholders; deleting them here produced broken "Hey !" copy.
  const sanitized = useMemo(() => text.trim(), [text]);

  return (
    <CardShell
      label={resolvedLabel}
      icon="message"
      accent={false}
      headerActions={<CopyButton text={sanitized} />}
    >
      <Text style={s.body} selectable>
        {sanitized}
      </Text>
    </CardShell>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    body: { ...Type.body, color: t.text },
  });
}
