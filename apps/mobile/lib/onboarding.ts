/** Onboarding is a non-secret device preference; auth credentials stay in SecureStore. */
import { prefFilePath, readPrefFile, writePrefFile } from "@/lib/filePrefs";

const FILE_NAME = "recall.onboarded.txt";

let cached: boolean | null = null;
let generation = 0;
let writes: Promise<void> = Promise.resolve();

function persist(value: boolean, expectedGeneration: number): Promise<void> {
  writes = writes.then(async () => {
    if (generation !== expectedGeneration) return;
    await writePrefFile(prefFilePath(FILE_NAME), value ? "1" : "0");
  });
  return writes;
}

export async function getOnboarded(): Promise<boolean> {
  if (cached !== null) return cached;
  const expectedGeneration = generation;
  const stored = await readPrefFile(prefFilePath(FILE_NAME));
  if (generation !== expectedGeneration) return cached ?? false;
  cached = stored === "1";
  return cached;
}

export async function setOnboarded(): Promise<void> {
  cached = true;
  await persist(true, ++generation);
}

export async function clearOnboarded(): Promise<void> {
  cached = false;
  await persist(false, ++generation);
}
