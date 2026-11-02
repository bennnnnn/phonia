import { useMemo } from "react";
import {
  ActivityIndicator,
  Image,
  Platform,
  Pressable,
  type PressableStateCallbackType,
  StyleSheet,
  Text,
  View,
  type ViewStyle,
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Redirect } from "expo-router";
import { useTranslation } from "react-i18next";

import { AuthScrollLayout } from "@/components/AuthScrollLayout";
import { Button } from "@/ui/controls/Button";
import { BrandMark } from "@/ui/icons/brand";
import { Icon } from "@/ui/icons/Icon";
import { useAuth } from "@/contexts/AuthContext";
import { type LoginProvider, useLoginActions } from "@/features/auth/hooks/useLoginActions";
import { AI_CONSENT_ROUTE, needsAiDataConsent } from "@/features/auth/model/aiConsent";
import { shouldShowAppleSignInButton } from "@/lib/apple-auth";
import { config, isGoogleSignInConfigured, isGoogleWebClientConfigured } from "@/lib/config";
import { isExpoGo } from "@/lib/google-auth";
import { getLegalPrivacyUrl, getLegalTermsUrl } from "@/lib/legalUrls";
import { openAllowedUrl } from "@/lib/linkSchemePolicy";
import { Space } from "@/lib/space";
import { shadowGlow } from "@/lib/shadow";
import { Theme, useTheme, withAlpha } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { IconSize } from "@/ui/icons/sizes";
import { Radius } from "@/lib/radius";

/** Frosted-glass tint over the hero gradient — deliberately theme-invariant
 * white, unlike the primary-tinted border below (which DOES follow theme). */
// eslint-disable-next-line no-restricted-syntax -- frosted glass is white in both schemes; no theme role means that
const GLASS_WHITE = "#FFFFFF";

const APP_ICON = require("@/assets/images/icon.png");
/** A 12pt link line is about 17pt tall: this makes it a 45pt target, short of the next link. */
const LEGAL_LINK_SLOP = { top: 14, bottom: 14, left: Space.xs, right: Space.xs };

const HIGHLIGHTS = [
  { icon: "graduation-cap" as const, labelKey: "login.highlight_learn" },
  { icon: "calendar" as const, labelKey: "login.highlight_organize" },
];

export default function LoginScreen() {
  const { token, user, loading, onboarded } = useAuth();
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const { busyProvider, busy, handleApple, handleGoogle, handleDev } =
    useLoginActions();
  const showDevLogin = config.devAuthEnabled && __DEV__;
  const showGoogleLogin =
    !isExpoGo() &&
    (Platform.OS === "android" ? isGoogleWebClientConfigured() : isGoogleSignInConfigured());
  const showAppleLogin = shouldShowAppleSignInButton();
  const googleOnlyDevBuild = !isExpoGo() && showDevLogin && showGoogleLogin;
  // Expo Go signs in with neither Google nor Apple: dev login is the way in there.
  const expoGo = isExpoGo();
  /** Another provider's sign-in dims this button; a press shows only while none is busy. */
  const providerStyle =
    (base: ViewStyle, provider: LoginProvider) => ({ pressed }: PressableStateCallbackType) => [
      base,
      busyProvider !== null && busyProvider !== provider && s.dim,
      pressed && busyProvider === null && s.pressed,
    ];
  const devBanner = (message: string) => (
    <View style={s.devBanner}>
      <Icon name="info" size={IconSize.sm} color={theme.primary} />
      <Text style={s.devBannerText}>{message}</Text>
    </View>
  );
  /** Dev login as the only way in (Expo Go on Android, or no sign-in configured). */
  const devPrimaryLogin = (
    <Button
      title={t("login.dev")}
      onPress={handleDev}
      loading={busyProvider === "dev"}
      loadingLabel={t("login.dev")}
      disabled={busy}
      style={s.primaryBtn}
    />
  );
  /** Dev login under a real sign-in button. */
  const devSecondaryLogin = (
    <>
      <Text style={s.orText}>{t("login.or_dev")}</Text>
      <Pressable
        style={providerStyle(s.devSecondaryBtn, "dev")}
        onPress={handleDev}
        disabled={busy}
        accessibilityRole="button"
        accessibilityLabel={t("login.dev")}
        accessibilityState={{ disabled: busy, busy: busyProvider === "dev" }}
      >
        {busyProvider === "dev" ? (
          <ActivityIndicator size="small" color={theme.primary} />
        ) : (
          <Text style={s.devSecondaryText}>{t("login.dev")}</Text>
        )}
      </Pressable>
    </>
  );

  if (loading) {
    return (
      <View style={s.center}>
        <ActivityIndicator size="large" color={theme.primary} />
      </View>
    );
  }

  // A tap here agrees, so a sign-in comes back agreed and opens the chat. An account the
  // server answers without it (an older API) still sees the consent screen first.
  if (token) return <Redirect href={needsAiDataConsent(user) ? AI_CONSENT_ROUTE : "/"} />;
  if (!onboarded) return <Redirect href="/onboarding" />;

  const gradientColors = [theme.primaryLight, theme.bg] as const;

  return (
    <LinearGradient colors={gradientColors} style={s.root}>
      <AuthScrollLayout justify="space-between">
        <View style={s.hero}>
          <View style={s.logoGlow}>
            <Image source={APP_ICON} style={s.logo} accessibilityLabel={t("app.name")} />
          </View>
          <Text style={s.title} accessibilityRole="header">{t("app.name")}</Text>
          <Text style={s.subtitle}>{t("login.tagline")}</Text>

          <View style={s.highlights}>
            {HIGHLIGHTS.map((item) => (
              <View key={item.labelKey} style={s.highlight}>
                <View style={s.highlightIcon}>
                  <Icon name={item.icon} size={IconSize.xs} color={theme.primary} />
                </View>
                <Text style={s.highlightText}>{t(item.labelKey)}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={s.actions}>
          {expoGo && showDevLogin ? (
            <>
              {devBanner(t(Platform.OS === "ios" ? "login.dev_expo_ios_hint" : "login.dev_expo_hint"))}
              {devPrimaryLogin}
            </>
          ) : (
            <>
              {showAppleLogin ? (
                <Pressable
                  style={providerStyle(s.appleBtn, "apple")}
                  onPress={handleApple}
                  disabled={busy}
                  accessibilityRole="button"
                  accessibilityLabel={t("login.apple")}
                  accessibilityState={{ disabled: busy, busy: busyProvider === "apple" }}
                >
                  {busyProvider === "apple" ? (
                    <ActivityIndicator color={theme.brand.appleInk} />
                  ) : (
                    <>
                      <BrandMark name="apple" size={IconSize.sm} color={theme.brand.appleInk} />
                      <Text style={s.appleText}>{t("login.apple")}</Text>
                    </>
                  )}
                </Pressable>
              ) : null}
              {showGoogleLogin ? (
                <Pressable
                  style={providerStyle(s.googleBtn, "google")}
                  onPress={handleGoogle}
                  disabled={busy}
                  accessibilityRole="button"
                  accessibilityLabel={t("login.google")}
                  accessibilityState={{ disabled: busy, busy: busyProvider === "google" }}
                >
                  {busyProvider === "google" ? (
                    <ActivityIndicator color={theme.textSecondary} />
                  ) : (
                    <>
                      <BrandMark name="google" size={IconSize.sm} />
                      <Text style={s.googleText}>{t("login.google")}</Text>
                    </>
                  )}
                </Pressable>
              ) : showDevLogin && !showAppleLogin ? (
                devBanner(t("login.error_not_configured"))
              ) : null}
              {googleOnlyDevBuild ? (
                devSecondaryLogin
              ) : showDevLogin && !showGoogleLogin && !showAppleLogin ? (
                devPrimaryLogin
              ) : null}
            </>
          )}

          {/* Apple 5.1.2(i): the disclosure sits under the buttons and a tap is the
              agreement (features/auth/api.ts sends it with the sign-in). */}
          <Text style={s.consentLine}>{t("login.consent_line")}</Text>
          <View style={s.links}>
            <Pressable
              onPress={() => void openAllowedUrl(getLegalTermsUrl())}
              accessibilityRole="link"
              accessibilityLabel={t("login.terms")}
              hitSlop={LEGAL_LINK_SLOP}
            >
              <Text style={[s.link, s.linkPressable]}>{t("login.terms")}</Text>
            </Pressable>
            <Text style={s.dot} accessibilityElementsHidden importantForAccessibility="no">·</Text>
            <Pressable
              onPress={() => void openAllowedUrl(getLegalPrivacyUrl())}
              accessibilityRole="link"
              accessibilityLabel={t("login.privacy")}
              hitSlop={LEGAL_LINK_SLOP}
            >
              <Text style={[s.link, s.linkPressable]}>{t("login.privacy")}</Text>
            </Pressable>
          </View>
        </View>
      </AuthScrollLayout>
    </LinearGradient>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    center: {
      flex: 1,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: theme.bg,
    },
    root: { flex: 1 },
    hero: {
      flex: 1,
      alignItems: "center",
      justifyContent: "center",
      paddingTop: Space.sm,
      paddingBottom: Space.lg,
    },
    logoGlow: {
      borderRadius: Radius.composer,
      marginBottom: Space.gutter,
      ...shadowGlow(theme, theme.primary),
    },
    logo: {
      width: 88,
      height: 88,
      borderRadius: Radius.composer,
    },
    title: {
      ...Type.display,
      color: theme.text,
    },
    subtitle: {
      ...Type.body,
      color: theme.textSecondary,
      marginTop: Space.xs,
      textAlign: "center",
      maxWidth: 300,
      paddingHorizontal: Space.xs,
    },
    highlights: {
      flexDirection: "row",
      flexWrap: "wrap",
      justifyContent: "center",
      gap: Space.xs,
      marginTop: Space.lg,
      maxWidth: 340,
    },
    highlight: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xs,
      backgroundColor: theme.isDark ? theme.surface : withAlpha(GLASS_WHITE, 0.72),
      borderRadius: Radius.full,
      paddingHorizontal: Space.sm,
      paddingVertical: Space.xs,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.isDark ? theme.border : withAlpha(theme.primary, 0.12),
    },
    highlightIcon: {
      width: 24,
      height: 24,
      borderRadius: Radius.md,
      backgroundColor: theme.primaryLight,
      alignItems: "center",
      justifyContent: "center",
    },
    highlightText: {
      ...Type.caption,
      color: theme.textSecondary,
    },
    actions: {
      paddingBottom: Space.xs,
      gap: Space.sm,
    },
    devBanner: {
      flexDirection: "row",
      alignItems: "flex-start",
      gap: Space.xs,
      backgroundColor: withAlpha(GLASS_WHITE, theme.isDark ? 0.08 : 0.5),
      borderRadius: Radius.lg,
      paddingHorizontal: Space.sm,
      paddingVertical: Space.sm,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.isDark
        ? withAlpha(GLASS_WHITE, 0.1)
        : withAlpha(theme.primary, 0.12),
    },
    devBannerText: {
      flex: 1,
      ...Type.caption,
      ...Weight.regular,
      lineHeight: 19,
      color: theme.textSecondary,
    },
    primaryBtn: {
      alignSelf: "stretch",
      width: "100%",
    },
    appleBtn: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "center",
      gap: Space.xs,
      width: "100%",
      borderRadius: Radius.xl,
      paddingVertical: Space.md,
      backgroundColor: theme.brand.apple,
    },
    appleText: { ...Type.body, ...Weight.semibold, color: theme.brand.appleInk },
    googleBtn: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "center",
      gap: Space.xs,
      width: "100%",
      borderRadius: Radius.xl,
      borderWidth: 1.5,
      borderColor: theme.isDark
        ? withAlpha(GLASS_WHITE, 0.12)
        : withAlpha(theme.primary, 0.18),
      paddingVertical: Space.md,
      backgroundColor: withAlpha(GLASS_WHITE, theme.isDark ? 0.08 : 0.55),
    },
    googleText: { ...Type.body, ...Weight.semibold, color: theme.text },
    orText: {
      ...Type.caption,
      color: theme.textTertiary,
      textAlign: "center",
    },
    devSecondaryBtn: {
      alignItems: "center",
      justifyContent: "center",
      width: "100%",
      borderRadius: Radius.xl,
      borderWidth: 1.5,
      borderColor: theme.isDark
        ? withAlpha(GLASS_WHITE, 0.12)
        : withAlpha(theme.primary, 0.18),
      paddingVertical: Space.sm,
      backgroundColor: withAlpha(GLASS_WHITE, theme.isDark ? 0.06 : 0.45),
    },
    devSecondaryText: { ...Type.secondary, ...Weight.semibold, color: theme.primary },
    dim: { opacity: 0.55 },
    pressed: { opacity: 0.85 },
    consentLine: {
      ...Type.caption,
      ...Weight.regular,
      color: theme.textSecondary,
      textAlign: "center",
      paddingHorizontal: Space.xs,
    },
    links: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "center",
      gap: Space.xs,
      marginTop: 2,
    },
    link: { ...Type.caption, ...Weight.regular, color: theme.primary },
    linkPressable: { textDecorationLine: "underline" },
    dot: { ...Type.caption, ...Weight.regular, color: theme.textTertiary },
  });
}
