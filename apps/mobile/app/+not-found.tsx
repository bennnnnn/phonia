import { Link, Stack } from "expo-router";
import { useMemo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";

export default function NotFoundScreen() {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);

  return (
    <>
      <Stack.Screen options={{ title: t("common.error") }} />
      <View style={s.container}>
        <Text style={s.title} accessibilityRole="header">{t("common.not_found_title")}</Text>
        <Link href="/" asChild>
          <Pressable style={s.link}>
            <Text style={s.linkText}>{t("common.not_found_home")}</Text>
          </Pressable>
        </Link>
      </View>
    </>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    container: {
      flex: 1,
      alignItems: "center",
      justifyContent: "center",
      padding: Space.md,
      backgroundColor: theme.bg,
    },
    title: {
      ...Type.title,
      color: theme.text,
      textAlign: "center",
    },
    link: {
      marginTop: Space.md,
      paddingVertical: Space.md,
    },
    linkText: {
      ...Type.secondary,
      ...Weight.semibold,
      color: theme.primary,
    },
  });
}
