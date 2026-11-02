import { useAccountSession } from "@/contexts/accountSession";
import { useEffect, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { Icon } from "@/ui/icons/Icon";
import { Sheet } from "@/ui/overlay/Sheet";
import { Button } from "@/ui/controls/Button";
import { useSubscriptionActions } from "@/features/billing/hooks/useSubscriptionActions";
import type { IconName } from "@/ui/icons/names";
import { api } from "@/lib/api";
import { reportFailure } from "@/lib/sentry";
import {
  getPlanPackages,
  isPurchaseCancelled,
  isPurchasesConfigured,
  type PlanOffer,
  purchasePlanPackage,
  restorePurchases,
} from "@/features/billing/model/purchases";
import {
  type PaidPlanId,
  type PlanCatalog,
  type PlanId,
  type PlanInfo,
  planNameKey,
  planOf,
  premiumModelNames,
  upgradeTargets,
} from "@/lib/plan";
import { Space } from "@/lib/space";
import { trackProductEvent } from "@/lib/productAnalytics";
import { getLegalPrivacyUrl, getLegalTermsUrl } from "@/lib/legalUrls";
import { openAllowedUrl } from "@/lib/linkSchemePolicy";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { IconSize } from "@/ui/icons/sizes";
import { Radius } from "@/lib/radius";

export type UpgradeSource = "quota" | "model_gate" | "settings" | "voice" | "live_talk" | "other";

type Props = {
  visible: boolean;
  onClose: () => void;
  source?: UpgradeSource;
};

type Translate = (key: string, options?: Record<string, unknown>) => string;

const PLAN_RANK: Record<PlanId, number> = { free: 0, plus: 1, pro: 2 };

const NO_OFFER: PlanOffer = { packages: {}, unavailable: false };
/** A 12pt link line is about 17pt tall: this makes it a 45pt target, short of the next link. */
const LEGAL_LINK_SLOP = { top: 14, bottom: 14, left: Space.xs, right: Space.xs };

type FeatureLine = { icon: IconName; text: string };

/** The paid models by name when the server's list is in, else a line that names none. */
function modelsLine(models: readonly string[], t: Translate): string {
  return models.length ? t("upgrade.feature_models_named", { models: models.join(", ") }) : t("upgrade.feature_models");
}

/** What a plan includes, with the server's numbers (the store owns the price). */
function planFeatureLines(
  plan: PaidPlanId,
  info: PlanInfo | undefined,
  models: readonly string[],
  t: Translate,
): FeatureLine[] {
  const lines: FeatureLine[] = [];
  const images = info?.allowances.daily_image_generations;
  if (plan === "pro") {
    lines.push({ icon: "check", text: t("upgrade.everything_in", { plan: t(planNameKey("plus")) }) });
    const minutes = info?.allowances.monthly_live_talk_minutes;
    lines.push({
      icon: "activity",
      text: minutes ? t("upgrade.feature_live_talk", { count: minutes }) : t("upgrade.feature_live_talk_plain"),
    });
  } else {
    lines.push({ icon: "zap", text: modelsLine(models, t) });
    lines.push({ icon: "infinity", text: t("upgrade.feature_limits") });
    lines.push({ icon: "mic", text: t("upgrade.feature_voice") });
  }
  if (images) lines.push({ icon: "image", text: t("upgrade.feature_images", { count: images }) });
  return lines;
}

export function UpgradeSheet({ visible, onClose, source = "other" }: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = makeStyles(theme);
  const { token, user, syncSubscription, devUpgrade } = useSubscriptionActions();
  const { account, getToken } = useAccountSession();
  const current = planOf(user);
  const targets = upgradeTargets(current);
  const [offer, setOffer] = useState<PlanOffer>(NO_OFFER);
  const [offerAttempt, setOfferAttempt] = useState(0);
  const packages = offer.packages;
  const [catalog, setCatalog] = useState<PlanCatalog | null>(null);
  const [premiumModels, setPremiumModels] = useState<string[]>([]);
  const [loadingOffer, setLoadingOffer] = useState(false);
  const [busy, setBusy] = useState<PaidPlanId | "restore" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const purchasesReady = isPurchasesConfigured();
  const wasVisible = useRef(false);

  useEffect(() => {
    if (visible && !wasVisible.current) {
      trackProductEvent("paywall_viewed", { source });
      setError(null);
    }
    wasVisible.current = visible;
  }, [source, visible]);

  useEffect(() => {
    const token = getToken();
    if (!visible || !account || !token) return;
    let cancelled = false;
    void api
      .listPlans(token)
      .then((next) => {
        if (!cancelled) setCatalog(next);
      })
      // The cards still show what each plan includes, without numbers.
      .catch((error: unknown) => reportFailure("paywall_load", error));
    void api
      .listModels(token)
      .then((models) => {
        if (!cancelled) setPremiumModels(premiumModelNames(models));
      })
      // Without the list the models line names no model.
      .catch((error: unknown) => reportFailure("paywall_load", error));
    return () => {
      cancelled = true;
    };
  }, [visible, account, getToken]);

  useEffect(() => {
    if (!visible || !purchasesReady) {
      setOffer(NO_OFFER);
      return;
    }
    let cancelled = false;
    setLoadingOffer(true);
    void getPlanPackages()
      .then((next) => {
        if (!cancelled) setOffer(next);
      })
      .finally(() => {
        if (!cancelled) setLoadingOffer(false);
      });
    return () => {
      cancelled = true;
    };
  }, [visible, purchasesReady, offerAttempt]);

  /** The server reads the store again. The store took the payment, so a failure here says
   * "pending", never that it failed: the plan listener and the webhook still land it. */
  const syncAfterStore = async () => {
    if (!token) return;
    try {
      await syncSubscription();
      onClose();
    } catch (error) {
      reportFailure("purchase_sync", error);
      setError(t("upgrade.sync_pending"));
    }
  };

  const onSubscribe = async (plan: PaidPlanId) => {
    const pkg = packages[plan];
    if (!token || !pkg || busy) return;
    setBusy(plan);
    setError(null);
    trackProductEvent("purchase_started", { plan });
    let purchased: PlanId = "free";
    try {
      purchased = await purchasePlanPackage(pkg);
    } catch (purchaseError) {
      const cancelled = isPurchaseCancelled(purchaseError);
      trackProductEvent("purchase_failed", {
        plan,
        reason: cancelled ? "cancelled" : "error",
      });
      if (!cancelled) reportFailure("purchase", purchaseError);
      if (!cancelled) setError(t("upgrade.purchase_failed"));
      setBusy(null);
      return;
    }
    if (PLAN_RANK[purchased] < PLAN_RANK[plan]) {
      trackProductEvent("purchase_failed", { plan, reason: "error" });
      setError(t("upgrade.purchase_failed"));
      setBusy(null);
      return;
    }
    trackProductEvent("purchase_succeeded", { plan });
    await syncAfterStore();
    setBusy(null);
  };

  const onRestore = async () => {
    if (!token || busy) return;
    setBusy("restore");
    setError(null);
    try {
      const restored = await restorePurchases();
      if (restored === "free") {
        setError(t("upgrade.restore_empty"));
        return;
      }
      await syncAfterStore();
    } catch (error) {
      reportFailure("purchase_restore", error);
      setError(t("upgrade.purchase_failed"));
    } finally {
      setBusy(null);
    }
  };

  const planInfo = (plan: PaidPlanId) => catalog?.plans.find((item) => item.id === plan);

  return (
    <Sheet
      visible={visible}
      onClose={onClose}
      minBottomPadding={36}
      contentContainerStyle={s.sheet}
    >
      <View style={s.iconWrap}>
        <Icon name="sparkles" size={IconSize.lg} color={theme.primary} />
      </View>
      <Text style={s.title} accessibilityRole="header">{t("upgrade.title")}</Text>
      {current !== "free" ? (
        <Text style={s.body}>{t("upgrade.current_plan", { plan: t(planNameKey(current)) })}</Text>
      ) : (
        <Text style={s.body}>{t("upgrade.body")}</Text>
      )}
      {targets.map((plan) => {
        const pkg = packages[plan];
        const price = pkg?.priceString;
        return (
          <View key={plan} style={s.card} testID={`upgrade-plan-${plan}`}>
            <View style={s.cardHeader}>
              <Text style={s.cardTitle}>{t(planNameKey(plan))}</Text>
              <Text style={s.cardPrice}>
                {price ? t("upgrade.per_month", { price }) : t("upgrade.price_fallback")}
              </Text>
            </View>
            <View style={s.featureList}>
              {planFeatureLines(plan, planInfo(plan), premiumModels, t).map((line) => (
                <FeatureRow key={line.text} icon={line.icon} text={line.text} theme={theme} />
              ))}
            </View>
            {purchasesReady ? (
              <Button
                title={t("upgrade.subscribe_plan", { plan: t(planNameKey(plan)) })}
                onPress={() => void onSubscribe(plan)}
                loading={busy === plan || (loadingOffer && !pkg)}
                disabled={!pkg || (busy != null && busy !== plan)}
                variant={plan === "pro" ? "primary" : "secondary"}
                style={s.primaryBtn}
              />
            ) : null}
          </View>
        );
      })}
      {purchasesReady && offer.unavailable && !loadingOffer ? (
        <>
          <Text style={s.error}>{t("upgrade.store_unavailable")}</Text>
          <Button
            title={t("common.retry")}
            onPress={() => setOfferAttempt((attempt) => attempt + 1)}
            variant="secondary"
            style={s.primaryBtn}
          />
        </>
      ) : null}
      {error ? <Text style={s.error}>{error}</Text> : null}
      {purchasesReady ? (
        <Button
          title={t("upgrade.restore")}
          onPress={() => void onRestore()}
          variant="ghost"
          loading={busy === "restore"}
          disabled={busy != null && busy !== "restore"}
        />
      ) : (
        // A build with no store keys (Expo Go, a local build) cannot sell: say so, never "Coming soon".
        <Text style={s.storeMissing}>{t("upgrade.store_not_in_build")}</Text>
      )}
      <Text style={s.subscriptionTerms}>{t("upgrade.subscription_terms")}</Text>
      <View style={s.legalLinks}>
        <Pressable
          onPress={() => void openAllowedUrl(getLegalTermsUrl())}
          accessibilityRole="link"
          accessibilityLabel={t("terms.title")}
          hitSlop={LEGAL_LINK_SLOP}
        >
          <Text style={s.legalLink}>{t("terms.title")}</Text>
        </Pressable>
        <Text style={s.legalSeparator} accessibilityElementsHidden importantForAccessibility="no">·</Text>
        <Pressable
          onPress={() => void openAllowedUrl(getLegalPrivacyUrl())}
          accessibilityRole="link"
          accessibilityLabel={t("privacy.title")}
          hitSlop={LEGAL_LINK_SLOP}
        >
          <Text style={s.legalLink}>{t("privacy.title")}</Text>
        </Pressable>
      </View>
      {__DEV__
        ? targets.map((plan) => (
            <Pressable
              key={`dev-${plan}`}
              style={s.devBtn}
              accessibilityRole="button"
              onPress={() => {
                void devUpgrade(plan).then((ok) => {
                  if (ok) onClose();
                });
              }}
            >
              <Text style={s.devBtnText}>
                {t("upgrade.dev_enable_plan", { plan: t(planNameKey(plan)) })}
              </Text>
            </Pressable>
          ))
        : null}
    </Sheet>
  );
}

function FeatureRow({
  icon,
  text,
  theme,
}: {
  icon: IconName;
  text: string;
  theme: Theme;
}) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: Space.xs }}>
      <Icon name={icon} size={IconSize.sm} color={theme.primary} />
      <Text style={{ flex: 1, ...Type.secondary, color: theme.textSecondary }}>{text}</Text>
    </View>
  );
}

const makeStyles = (theme: Theme) =>
  StyleSheet.create({
    sheet: {
      backgroundColor: theme.bg,
      paddingHorizontal: Space.lg,
      paddingTop: Space.lg,
      gap: Space.sm,
    },
    iconWrap: {
      width: 52,
      height: 52,
      borderRadius: Radius.full,
      backgroundColor: theme.primaryLight,
      alignItems: "center",
      justifyContent: "center",
      alignSelf: "center",
    },
    title: {
      ...Type.h1,
      color: theme.text,
      textAlign: "center",
    },
    body: {
      ...Type.secondary,
      color: theme.textSecondary,
      textAlign: "center",
    },
    card: {
      borderRadius: Radius.lg,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
      backgroundColor: theme.surface,
      padding: Space.md,
      gap: Space.xs,
    },
    cardHeader: {
      flexDirection: "row",
      alignItems: "baseline",
      justifyContent: "space-between",
      gap: Space.xs,
    },
    cardTitle: {
      ...Type.body,
      ...Weight.semibold,
      color: theme.text,
    },
    cardPrice: {
      ...Type.secondary,
      color: theme.textSecondary,
    },
    featureList: { gap: Space.xs, marginVertical: Space.xxs },
    error: {
      ...Type.secondary,
      color: theme.danger,
      textAlign: "center",
    },
    primaryBtn: {
      marginTop: Space.xxs,
    },
    storeMissing: {
      ...Type.secondary,
      color: theme.textSecondary,
      textAlign: "center",
    },
    subscriptionTerms: {
      ...Type.caption,
      color: theme.textTertiary,
      textAlign: "center",
      lineHeight: 17,
    },
    legalLinks: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "center",
      gap: Space.xs,
    },
    legalLink: {
      ...Type.caption,
      color: theme.primary,
      ...Weight.semibold,
    },
    legalSeparator: {
      ...Type.caption,
      color: theme.textTertiary,
    },
    devBtn: {
      alignItems: "center",
      paddingVertical: Space.xs,
    },
    devBtnText: { ...Type.compact, color: theme.textTertiary },
  });
