/**
 * Plans as the app sees them. The server decides what a plan includes
 * (`user.features`) and refuses anything else; these helpers only choose
 * what to show. Display names live in i18n (`plans.<id>`), never in code.
 */

export type PlanId = "free" | "plus" | "pro";
export type PaidPlanId = Exclude<PlanId, "free">;

export type PlanFeature =
  | "all_models"
  | "image_generation"
  | "speech_transcription"
  | "speech_tts"
  | "live_talk";

type PlanAllowance =
  | "daily_tokens"
  | "daily_image_uploads"
  | "daily_web_searches"
  | "daily_image_searches"
  | "daily_image_generations"
  | "daily_speech_transcriptions"
  | "daily_speech_tts"
  | "monthly_live_talk_minutes";

export type PlanInfo = {
  id: PlanId;
  features: PlanFeature[];
  allowances: Partial<Record<PlanAllowance, number>>;
};

export type PlanCatalog = {
  current: PlanId;
  plans: PlanInfo[];
};

type PlanHolder = { plan?: string | null; features?: readonly string[] | null } | null | undefined;

export function planOf(holder: PlanHolder): PlanId {
  const plan = holder?.plan;
  return plan === "plus" || plan === "pro" ? plan : "free";
}

/** Before the server lists features (an older cached user), assume the defaults. */
function fallbackFeatures(plan: PlanId): PlanFeature[] {
  if (plan === "free") return ["image_generation"];
  const paid: PlanFeature[] = ["all_models", "image_generation", "speech_transcription", "speech_tts"];
  return plan === "pro" ? [...paid, "live_talk"] : paid;
}

export function hasPlanFeature(holder: PlanHolder, feature: PlanFeature): boolean {
  const features = holder?.features;
  if (Array.isArray(features)) return features.includes(feature);
  return fallbackFeatures(planOf(holder)).includes(feature);
}

/** The plan to offer next: free sees both, Plus sees Pro, Pro sees none. */
export function upgradeTargets(current: PlanId): PaidPlanId[] {
  if (current === "free") return ["plus", "pro"];
  if (current === "plus") return ["pro"];
  return [];
}

export function planNameKey(plan: PlanId): `plans.${PlanId}` {
  return `plans.${plan}`;
}

/**
 * The names of the models a paid plan unlocks, from the server's model list, so the
 * paywall never names a model that does not exist or is free.
 */
export function premiumModelNames(
  models: readonly { label: string; plan_access: string; available: boolean }[],
): string[] {
  return models.filter((model) => model.plan_access === "pro" && model.available).map((model) => model.label);
}
