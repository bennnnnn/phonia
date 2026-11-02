import type { ModelInfo } from "@/lib/api/types";
import { cacheFile } from "@/lib/cache/cacheFile";

const cachedModelsFile = cacheFile("cached-models.json");

/** The catalog fields of a /models entry. Live health is left out: a days-old
 * "degraded" must not show before the next fetch. */
type CachedModel = Pick<
  ModelInfo,
  "id" | "label" | "description" | "tier" | "plan_access" | "available"
>;

/** Tagged with the account that fetched it, so a file that survives a failed
 * signout deletion is never shown to the next account. */
type CachedModels = { user_id: string; models: CachedModel[] };

function catalogEntry(model: ModelInfo): CachedModel {
  const { id, label, description, tier, plan_access, available } = model;
  return { id, label, description, tier, plan_access, available };
}

function readEntry(value: unknown): CachedModel | null {
  if (typeof value !== "object" || value === null) return null;
  const { id, label, description, tier, plan_access: planAccess, available } =
    value as Record<string, unknown>;
  if (
    typeof id !== "string" ||
    typeof label !== "string" ||
    typeof description !== "string" ||
    typeof tier !== "string" ||
    typeof available !== "boolean" ||
    (planAccess !== "free" && planAccess !== "pro")
  ) {
    return null;
  }
  return { id, label, description, tier, plan_access: planAccess, available };
}

/** The last catalog this account received from /models, to paint the model
 * list on cold start and offline. Null when there is none, it is unreadable,
 * or another account cached it. */
export async function readCachedModels(userId: string): Promise<ModelInfo[] | null> {
  const raw = await cachedModelsFile.read();
  if (raw === null) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return null;
    const { user_id: owner, models } = parsed as Record<string, unknown>;
    if (owner !== userId || !Array.isArray(models)) return null;
    const entries = models
      .map(readEntry)
      .filter((entry): entry is CachedModel => entry !== null);
    return entries.length > 0 ? entries : null;
  } catch {
    return null;
  }
}

export function writeCachedModels(userId: string, models: ModelInfo[]): Promise<void> {
  const cached: CachedModels = { user_id: userId, models: models.map(catalogEntry) };
  return cachedModelsFile.write(JSON.stringify(cached));
}

export function clearCachedModels(): Promise<void> {
  return cachedModelsFile.clear();
}
