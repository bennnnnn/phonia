import { Platform } from "react-native";

import type { PurchasesPackage } from "react-native-purchases";

import { isExpoGo } from "@/lib/expoRuntime";
import type { PaidPlanId, PlanId } from "@/lib/plan";
import { reportStoreUnavailable } from "@/lib/sentry";

/**
 * RevenueCat entitlement per paid plan. "pro" keeps the single-plan id, so
 * existing subscribers stay on the top plan; the server maps the same ids.
 */
const PLAN_ENTITLEMENT_IDS: Record<PaidPlanId, string> = { plus: "plus", pro: "pro" };

/**
 * Package identifier per plan in the current RevenueCat offering. An offering
 * from the single-plan era (only a monthly package) is offered as Pro.
 */
const PLAN_PACKAGE_IDS: Record<PaidPlanId, string> = {
  plus: "plus_monthly",
  pro: "pro_monthly",
};

/** Opaque handle — keeps react-native-purchases out of the static import graph
 * (its types are erased at build time). */
type PlanPackage = {
  plan: PaidPlanId;
  /** Localized by the store ("$7.99", "7,99 €"); never hardcoded. */
  priceString: string;
  productId: string;
  native: PurchasesPackage;
};

type ActiveEntitlements = Record<string, { productIdentifier?: string } | undefined>;
type CustomerInfoLike = { entitlements: { active: ActiveEntitlements } };

type PurchasesModule = typeof import("react-native-purchases");
/** Android: the Plus subscription a Pro purchase replaces. */
type ProductChange = Parameters<PurchasesModule["default"]["purchasePackage"]>[2];

let purchasesModule: PurchasesModule | null | undefined;

function revenueCatApiKey(): string | null {
  if (Platform.OS === "ios") {
    const key = process.env.EXPO_PUBLIC_REVENUECAT_IOS_API_KEY?.trim();
    return key || null;
  }
  if (Platform.OS === "android") {
    const key = process.env.EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY?.trim();
    return key || null;
  }
  return null;
}

export function isPurchasesConfigured(): boolean {
  if (isExpoGo()) return false;
  return revenueCatApiKey() != null;
}

export function isPurchaseCancelled(error: unknown): boolean {
  return Boolean(
    error &&
      typeof error === "object" &&
      "userCancelled" in error &&
      error.userCancelled === true,
  );
}

/** Highest plan the store says is active (what the server will also find). */
export function planFromCustomerInfo(info: CustomerInfoLike): PlanId {
  const active = info.entitlements.active;
  if (active[PLAN_ENTITLEMENT_IDS.pro] != null) return "pro";
  if (active[PLAN_ENTITLEMENT_IDS.plus] != null) return "plus";
  return "free";
}

async function loadPurchases(): Promise<PurchasesModule | null> {
  if (purchasesModule !== undefined) return purchasesModule;
  if (!isPurchasesConfigured()) {
    purchasesModule = null;
    return null;
  }
  try {
    purchasesModule = await import("react-native-purchases");
    return purchasesModule;
  } catch (error) {
    // A configured build without the store's native module: no plan can be bought.
    reportStoreUnavailable(error);
    purchasesModule = null;
    return null;
  }
}

/** App user id RevenueCat is set up for in this process (configure runs once). */
let configuredAppUserId: string | null = null;

export async function configurePurchases(appUserId: string): Promise<void> {
  const mod = await loadPurchases();
  const apiKey = revenueCatApiKey();
  if (!mod || !apiKey) return;
  if (configuredAppUserId === appUserId) return;
  if (configuredAppUserId == null) {
    mod.default.setLogLevel(__DEV__ ? mod.LOG_LEVEL.DEBUG : mod.LOG_LEVEL.WARN);
    await mod.default.configure({ apiKey, appUserID: appUserId });
  } else {
    // A second configure is unsupported; switching accounts is a logIn.
    await mod.default.logIn(appUserId);
  }
  configuredAppUserId = appUserId;
}

export type PlanOffer = {
  packages: Partial<Record<PaidPlanId, PlanPackage>>;
  /** The store could not be read, or sells no plan: say so and offer a retry. */
  unavailable: boolean;
};

const STORE_UNAVAILABLE: PlanOffer = { packages: {}, unavailable: true };

/**
 * The store's packages for each paid plan in the current offering. A failed read
 * is `unavailable`, never an empty offer that looks like "no products".
 */
export async function getPlanPackages(): Promise<PlanOffer> {
  const mod = await loadPurchases();
  if (!mod) return STORE_UNAVAILABLE;
  let offerings: Awaited<ReturnType<PurchasesModule["default"]["getOfferings"]>>;
  try {
    offerings = await mod.default.getOfferings();
  } catch (error) {
    reportStoreUnavailable(error);
    return STORE_UNAVAILABLE;
  }
  const offering = offerings.current;
  if (!offering) {
    reportStoreUnavailable(new Error("The store has no current offering"));
    return STORE_UNAVAILABLE;
  }
  const found: Partial<Record<PaidPlanId, PlanPackage>> = {};
  for (const pkg of offering.availablePackages) {
    for (const plan of ["plus", "pro"] as const) {
      if (pkg.identifier === PLAN_PACKAGE_IDS[plan]) {
        found[plan] = {
          plan,
          priceString: pkg.product.priceString,
          productId: pkg.product.identifier,
          native: pkg,
        };
      }
    }
  }
  if (!found.plus && !found.pro && offering.monthly) {
    found.pro = {
      plan: "pro",
      priceString: offering.monthly.product.priceString,
      productId: offering.monthly.product.identifier,
      native: offering.monthly,
    };
  }
  if (!found.plus && !found.pro) {
    reportStoreUnavailable(new Error("The store's offering holds no plan"));
    return STORE_UNAVAILABLE;
  }
  return { packages: found, unavailable: false };
}

/**
 * Buy a plan; resolves with the plan the store now reports. On Android a move
 * from Plus to Pro replaces the Plus subscription (prorated) instead of
 * stacking a second one; on iOS both live in one subscription group, so the
 * App Store does that itself.
 */
export async function purchasePlanPackage(pkg: PlanPackage): Promise<PlanId> {
  const mod = await loadPurchases();
  if (!mod) return "free";
  let productChange: ProductChange = null;
  if (Platform.OS === "android" && pkg.plan === "pro") {
    const info = await mod.default.getCustomerInfo();
    const plusProduct = info.entitlements.active[PLAN_ENTITLEMENT_IDS.plus]?.productIdentifier;
    const oldProduct = plusProduct?.split(":")[0];
    if (oldProduct && oldProduct !== pkg.productId.split(":")[0]) {
      productChange = {
        oldProductIdentifier: oldProduct,
        prorationMode: mod.default.PRORATION_MODE.IMMEDIATE_WITH_TIME_PRORATION,
      };
    }
  }
  const result = await mod.default.purchasePackage(pkg.native, null, productChange);
  return planFromCustomerInfo(result.customerInfo);
}

/** Restore store purchases; resolves with the plan they grant. */
export async function restorePurchases(): Promise<PlanId> {
  const mod = await loadPurchases();
  if (!mod) return "free";
  const info = await mod.default.restorePurchases();
  return planFromCustomerInfo(info);
}

/**
 * L4: log out RevenueCat so the next user doesn't inherit the prior user's
 * entitlements / customer info. No-op when Purchases isn't configured.
 */
export async function signOutRevenueCat(): Promise<void> {
  const mod = await loadPurchases();
  if (!mod) return;
  try {
    await mod.default.logOut();
  } catch {
    // best-effort — local token clear is what matters
  }
  // logOut leaves an anonymous id; the next sign-in logs in by app user id.
  if (configuredAppUserId != null) configuredAppUserId = "";
}

/**
 * Register a listener that fires when the store plan changes (free / plus /
 * pro). RevenueCat calls customerInfoUpdateListener on purchase/restore/expiry
 * and on app foreground; we de-dupe to only invoke `onChange` when the plan
 * actually changes, so callers don't spam a backend sync on every foreground.
 * The listener also fires once on registration with the current state —
 * that's intentional (gives a launch-time sync).
 *
 * Returns a cleanup that removes the listener, or null when Purchases isn't
 * available (Expo Go / web / no API key). */
export async function registerPlanChangeListener(
  onChange: (plan: PlanId) => void,
): Promise<(() => void) | null> {
  const mod = await loadPurchases();
  if (!mod) return null;
  let lastPlan: PlanId | null = null;
  const listener = (info: CustomerInfoLike) => {
    const plan = planFromCustomerInfo(info);
    if (plan === lastPlan) return;
    lastPlan = plan;
    onChange(plan);
  };
  mod.default.addCustomerInfoUpdateListener(listener);
  return () => {
    mod.default.removeCustomerInfoUpdateListener(listener);
  };
}
