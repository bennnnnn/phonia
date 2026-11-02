import { useMemo } from "react";
import { StyleSheet, Text } from "react-native";
import { useTranslation } from "react-i18next";

import { CopyButton } from "@/components/CopyButton";
import { CardShell } from "@/components/rich/CardShell";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

type Props = {
  text: string;
  /** i18n key of the card's label; a plain draft by default. */
  labelKey?: string;
};

/** Paste-ready text (a ```copy fence): the same card as the email and message drafts. */
export function CopyBlock({ text, labelKey = "rich.copy_draft" }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);

  return (
    <CardShell
      label={t(labelKey)}
      icon="file-text"
      accent={false}
      headerActions={<CopyButton text={text} />}
      testID="copy-block"
    >
      <Text style={s.body} selectable>
        {text}
      </Text>
    </CardShell>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    body: { ...Type.body, color: t.text },
  });
}
