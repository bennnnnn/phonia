import { useMemo } from "react";
import { StyleSheet } from "react-native";
import { useTranslation } from "react-i18next";

import { CardShell } from "@/components/rich/CardShell";
import { RichMathBody } from "@/components/rich/RichMathBody";
import { CalloutKind } from "@/lib/richBlocks";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

function calloutMeta(
  theme: Theme,
  t: (key: string) => string,
): Record<
  CalloutKind,
  {
    label: string;
    color: string;
    icon?: "info" | "warning" | "alert-circle";
  }
> {
  return {
    // Legacy ```tip fences still resolve here. No tip icon — the lightbulb is gone.
    tip: { label: t("rich.callout_tip"), color: theme.success },
    note: { label: t("rich.callout_note"), color: theme.primary, icon: "info" },
    info: { label: t("rich.callout_info"), color: theme.primary, icon: "info" },
    warning: { label: t("rich.callout_warning"), color: theme.warning, icon: "warning" },
    important: {
      label: t("rich.callout_important"),
      color: theme.danger,
      icon: "alert-circle",
    },
  };
}

type Props = { kind: CalloutKind; content: string };

export function CalloutBlock({ kind, content }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const meta = calloutMeta(theme, t)[kind] ?? calloutMeta(theme, t).note;

  // The title is always the kind (Note, Warning); every line is body. Taking
  // a multi-line callout's first sentence as the title hid what kind it was.
  return (
    <CardShell
      testID={`callout-${kind}`}
      label={meta.label}
      icon={meta.icon}
      accentColor={meta.color}
      iconColor={meta.color}
    >
      <RichMathBody content={content.trim()} style={s.body} />
    </CardShell>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    body: { ...Type.body, color: t.text },
  });
}
