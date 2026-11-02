import { useMemo, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Redirect, useRouter } from "expo-router";
import { useTranslation } from "react-i18next";

import { AuthScrollLayout } from "@/components/AuthScrollLayout";
import { Icon } from "@/ui/icons/Icon";
import { Button } from "@/ui/controls/Button";
import { useAuth } from "@/contexts/AuthContext";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { tap } from "@/lib/haptics";
import { Graphic } from "@/lib/graphic";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { IconSize } from "@/ui/icons/sizes";
import { Radius } from "@/lib/radius";
import { reportRecoverableError } from "@/lib/reportRecoverableError";

const FEATURES = [
  {
    icon: "message-dots",
    titleKey: "onboarding.chat_title",
    bodyKey: "onboarding.chat_body",
  },
  {
    icon: "sparkles",
    titleKey: "onboarding.remember_title",
    bodyKey: "onboarding.remember_body",
  },
] as const;

export default function Onboarding() {
  const { onboarded, completeOnboarding } = useAuth();
  const router = useRouter();
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const feedback = useActionFeedbackOptional();
  const [finishing, setFinishing] = useState(false);
  const finishingRef = useRef(false);

  if (onboarded) return <Redirect href="/login" />;

  const gradientColors = [theme.primaryLight, theme.bg] as const;

  const finish = async () => {
    if (finishingRef.current) return;
    tap();
    finishingRef.current = true;
    setFinishing(true);
    try {
      await completeOnboarding();
      router.replace("/login");
    } catch {
      reportRecoverableError(feedback, t("common.error"));
    } finally {
      finishingRef.current = false;
      setFinishing(false);
    }
  };

  return (
    <LinearGradient colors={gradientColors} style={s.root}>
      <AuthScrollLayout justify="center">
        <View style={s.hero}>
          <View style={s.badge}>
            <Text style={s.badgeStar} accessibilityElementsHidden importantForAccessibility="no">✦</Text>
          </View>
          <Text style={s.title} accessibilityRole="header">{t("onboarding.welcome")}</Text>
          <Text style={s.subtitle}>{t("onboarding.subtitle")}</Text>
        </View>

        <View style={s.features}>
          {FEATURES.map((f) => (
            <View key={f.titleKey} style={s.feature}>
              <View style={s.featureIcon}>
                <Icon name={f.icon} size={IconSize.sm} color={theme.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={s.featureTitle}>{t(f.titleKey)}</Text>
                <Text style={s.featureBody}>{t(f.bodyKey)}</Text>
              </View>
            </View>
          ))}
        </View>

        <Button
          title={t("onboarding.get_started")}
          onPress={() => void finish()}
          loading={finishing}
          loadingLabel={t("onboarding.get_started")}
          disabled={finishing}
          style={s.cta}
        />
      </AuthScrollLayout>
    </LinearGradient>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    root: {
      flex: 1,
    },
    hero: { alignItems: "center", marginBottom: Space.xl + Space.xs },
    badge: {
      width: 72,
      height: 72,
      borderRadius: Radius.composer,
      backgroundColor: theme.primary,
      alignItems: "center",
      justifyContent: "center",
      marginBottom: Space.md,
    },
    badgeStar: { ...Graphic.badgeMark, color: theme.onPrimary },
    title: {
      ...Type.display,
      color: theme.text,
    },
    subtitle: {
      ...Type.body,
      color: theme.textSecondary,
      marginTop: Space.xs,
      textAlign: "center",
    },
    features: { gap: Space.gutter, marginBottom: Space.xl + Space.xs },
    feature: { flexDirection: "row", alignItems: "flex-start", gap: Space.sm },
    featureIcon: {
      width: 40,
      height: 40,
      borderRadius: Radius.md,
      backgroundColor: theme.primaryLight,
      alignItems: "center",
      justifyContent: "center",
    },
    featureTitle: {
      ...Type.body,
      ...Weight.bold,
      color: theme.text,
      marginBottom: 2,
    },
    featureBody: { ...Type.label, ...Weight.regular, color: theme.textSecondary },
    cta: {
      alignSelf: "stretch",
    },
  });
}
