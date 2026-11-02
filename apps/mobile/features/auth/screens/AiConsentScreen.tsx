import { useMemo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Redirect } from "expo-router";
import { useTranslation } from "react-i18next";

import { AuthScrollLayout } from "@/components/AuthScrollLayout";
import { useAuth } from "@/contexts/AuthContext";
import { useAiConsentActions } from "@/features/auth/hooks/useAiConsentActions";
import { AI_CONSENT_ITEMS, needsAiDataConsent } from "@/features/auth/model/aiConsent";
import { getLegalPrivacyUrl } from "@/lib/legalUrls";
import { openAllowedUrl } from "@/lib/linkSchemePolicy";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { Button } from "@/ui/controls/Button";
import { Icon } from "@/ui/icons/Icon";
import { IconSize } from "@/ui/icons/sizes";

/**
 * What Recall sends to which outside service, with agree, sign out or delete. A
 * sign-in agrees by its tap (the line on LoginScreen), so this asks only an account
 * without the agreement: one from before that, or one that withdrew in Data controls.
 * Agreeing here keeps the user signed in; signing out leads back to the sign-in page,
 * whose tap agrees too.
 */
export default function AiConsentScreen() {
  const { token, user } = useAuth();
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const { busy, agree, decline, deleteAccount } = useAiConsentActions();

  if (!token) return <Redirect href="/login" />;
  if (!needsAiDataConsent(user)) return <Redirect href="/" />;

  const gradientColors = [theme.primaryLight, theme.bg] as const;

  return (
    <LinearGradient colors={gradientColors} style={s.root}>
      <AuthScrollLayout justify="space-between">
        <View>
          <View style={s.hero}>
            <View style={s.badge}>
              <Icon name="shield" size={IconSize.md} color={theme.onPrimary} />
            </View>
            <Text style={s.title} accessibilityRole="header">
              {t("onboarding.consent_title")}
            </Text>
            <Text style={s.intro}>{t("onboarding.consent_intro")}</Text>
          </View>

          <View style={s.items}>
            {AI_CONSENT_ITEMS.map((item) => (
              <View key={item.titleKey} style={s.item}>
                <View style={s.itemIcon}>
                  <Icon name={item.icon} size={IconSize.sm} color={theme.primary} />
                </View>
                <View style={s.itemText}>
                  <Text style={s.itemTitle}>{t(item.titleKey)}</Text>
                  <Text style={s.itemBody}>{t(item.bodyKey)}</Text>
                </View>
              </View>
            ))}
          </View>

          <Text style={s.footer}>{t("onboarding.consent_footer")}</Text>
          <Pressable
            onPress={() => void openAllowedUrl(getLegalPrivacyUrl())}
            accessibilityRole="link"
            accessibilityLabel={t("onboarding.consent_privacy_link")}
            hitSlop={13}
            style={s.linkWrap}
          >
            <Text style={s.link}>{t("onboarding.consent_privacy_link")}</Text>
          </Pressable>
        </View>

        <View style={s.actions}>
          <Button
            title={t("onboarding.consent_agree")}
            onPress={() => void agree()}
            size="lg"
            loading={busy === "agree"}
            loadingLabel={t("onboarding.consent_agree")}
            disabled={busy !== null}
            style={s.cta}
          />
          <Button
            title={t("onboarding.consent_decline")}
            onPress={() => void decline()}
            variant="ghost"
            loading={busy === "decline"}
            loadingLabel={t("onboarding.consent_decline")}
            disabled={busy !== null}
            style={s.cta}
          />
          <Button
            title={t("onboarding.consent_delete")}
            onPress={() => void deleteAccount()}
            variant="ghost"
            loading={busy === "delete"}
            loadingLabel={t("onboarding.consent_delete")}
            disabled={busy !== null}
            style={s.cta}
          />
        </View>
      </AuthScrollLayout>
    </LinearGradient>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    root: { flex: 1 },
    hero: { alignItems: "center", marginBottom: Space.lg },
    badge: {
      width: 56,
      height: 56,
      borderRadius: Radius.composer,
      backgroundColor: theme.primary,
      alignItems: "center",
      justifyContent: "center",
      marginBottom: Space.md,
    },
    title: { ...Type.display, color: theme.text, textAlign: "center" },
    intro: {
      ...Type.body,
      color: theme.textSecondary,
      marginTop: Space.xs,
      textAlign: "center",
    },
    items: { gap: Space.md, marginBottom: Space.lg },
    item: { flexDirection: "row", alignItems: "flex-start", gap: Space.sm },
    itemIcon: {
      width: 36,
      height: 36,
      borderRadius: Radius.md,
      backgroundColor: theme.primaryLight,
      alignItems: "center",
      justifyContent: "center",
    },
    itemText: { flex: 1 },
    itemTitle: { ...Type.body, ...Weight.bold, color: theme.text, marginBottom: 2 },
    itemBody: { ...Type.label, ...Weight.regular, color: theme.textSecondary },
    footer: { ...Type.label, ...Weight.regular, color: theme.textSecondary },
    linkWrap: { alignSelf: "flex-start", marginTop: Space.xs },
    link: { ...Type.label, color: theme.primary, textDecorationLine: "underline" },
    actions: { gap: Space.xs, marginTop: Space.lg },
    cta: { alignSelf: "stretch" },
  });
}
