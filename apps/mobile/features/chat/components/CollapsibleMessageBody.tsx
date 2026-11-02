import { ReactNode, useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useTranslation } from "react-i18next";

import { MESSAGE_FOLD_MAX_HEIGHT } from "@/lib/markdown/messageFold";
import { Theme, useTheme, withAlpha } from "@/lib/theme";
import { Type } from "@/lib/type";
import { Space } from "@/lib/space";

type Props = {
  children: ReactNode;
  /** When false, always show full content (short user bubbles). */
  collapsible?: boolean;
  /** Background matched by the fade gradient (defaults to screen bg). */
  fadeColor?: string;
};

export function CollapsibleMessageBody({
  children,
  collapsible = true,
  fadeColor,
}: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const [expanded, setExpanded] = useState(false);
  const fadeBase = fadeColor ?? theme.bg;

  if (!collapsible) {
    return <>{children}</>;
  }

  const folded = !expanded;

  return (
    <View style={s.wrap}>
      <View style={folded ? s.clipped : undefined}>{children}</View>
      {folded ? (
        <LinearGradient
          colors={[withAlpha(fadeBase, 0), withAlpha(fadeBase, 0.9), fadeBase]}
          style={s.fade}
          pointerEvents="none"
        />
      ) : null}
      <Pressable
        style={s.toggle}
        onPress={() => setExpanded((value) => !value)}
        hitSlop={8}
        accessibilityRole="button"
        accessibilityState={{ expanded }}
        accessibilityLabel={expanded ? t("common.show_less") : t("common.show_more")}
      >
        <Text style={s.toggleText}>
          {expanded ? t("common.show_less") : t("common.show_more")}
        </Text>
      </Pressable>
    </View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    wrap: {
      position: "relative",
      alignSelf: "stretch",
    },
    clipped: {
      maxHeight: MESSAGE_FOLD_MAX_HEIGHT,
      overflow: "hidden",
    },
    fade: {
      position: "absolute",
      left: 0,
      right: 0,
      bottom: 28,
      height: 48,
    },
    toggle: {
      alignSelf: "flex-start",
      paddingVertical: Space.xxs,
      marginTop: 2,
    },
    toggleText: {
      ...Type.label,
      color: theme.primary,
    },
  });
}
