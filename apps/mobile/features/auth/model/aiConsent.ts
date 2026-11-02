import type { IconName } from "@/ui/icons/names";
import type { User } from "@/lib/api/types";

/**
 * True when a signed-in account has not yet agreed to what Recall sends to outside
 * AI and search services (App Store 5.1.2(i), Play User Data). A sign-in from this
 * app agrees by its tap (features/auth/api.ts), so this is an account from before
 * that, or one that withdrew in Data controls. The server answers null until then. Undefined comes only from an older server or a
 * cold-start cache written before the field existed, and is let through so an
 * account that already agreed is never asked again while offline.
 */
export function needsAiDataConsent(
  user: Pick<User, "ai_data_consent_at"> | null | undefined,
): boolean {
  return user?.ai_data_consent_at === null;
}

export const AI_CONSENT_ROUTE = "/consent";

// Signed-out screens send a new sign-in on themselves (LoginScreen redirects it).
const ROUTES_WITHOUT_CONSENT_CHECK = new Set([AI_CONSENT_ROUTE, "/login", "/onboarding"]);

/** Where to send the app from ``pathname``: the consent screen, or nowhere. Covers
 * every signed-in route (chat, deep links, a notification tap), not just the chat. */
export function aiConsentRedirect(
  user: Pick<User, "ai_data_consent_at"> | null | undefined,
  pathname: string | null,
): typeof AI_CONSENT_ROUTE | null {
  if (!needsAiDataConsent(user)) return null;
  if (pathname !== null && ROUTES_WITHOUT_CONSENT_CHECK.has(pathname)) return null;
  return AI_CONSENT_ROUTE;
}

type ConsentItem = { icon: IconName; titleKey: string; bodyKey: string };

/** What goes where, in the order the consent screen lists it. Keep in step with
 * the privacy policy (apps/api/app/content/privacy_policy.py). */
export const AI_CONSENT_ITEMS: readonly ConsentItem[] = [
  {
    icon: "message-dots",
    titleKey: "onboarding.consent_chats_title",
    bodyKey: "onboarding.consent_chats_body",
  },
  {
    icon: "image",
    titleKey: "onboarding.consent_files_title",
    bodyKey: "onboarding.consent_files_body",
  },
  {
    icon: "scan",
    titleKey: "onboarding.consent_math_title",
    bodyKey: "onboarding.consent_math_body",
  },
  {
    icon: "mic",
    titleKey: "onboarding.consent_voice_title",
    bodyKey: "onboarding.consent_voice_body",
  },
  {
    icon: "search",
    titleKey: "onboarding.consent_search_title",
    bodyKey: "onboarding.consent_search_body",
  },
  {
    icon: "map-pin",
    titleKey: "onboarding.consent_location_title",
    bodyKey: "onboarding.consent_location_body",
  },
];
