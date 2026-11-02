import { cacheDirectory, deleteAsync, getInfoAsync, readDirectoryAsync } from "expo-file-system/legacy";

/**
 * Files in the cache directory that hold one account's content. Each writer names
 * its file with its prefix here, so sign-out can find every one, including those
 * left by an earlier app run.
 */
const ACCOUNT_FILE_PREFIX = {
  /** Settings → Data controls: the whole account export (chats, memories). */
  export: "recall-export-",
  /** A chat's HTML opened in the system browser. */
  htmlPreview: "recall-preview-",
  /** A reply read aloud; deleted after it plays, unless the app stopped first. */
  speech: "recall-tts-",
} as const;

/**
 * A file URI for `name` in `directory`. The legacy file system reads its URIs as URLs, so a
 * name with a space, an accent or "#" must be percent-encoded, or iOS refuses it.
 */
function fileUri(directory: string, name: string): string {
  return `${directory}${encodeURIComponent(name)}`;
}

/** A new file for `kind` in the cache directory; the caller has checked the directory exists. */
export function newAccountFile(kind: keyof typeof ACCOUNT_FILE_PREFIX, extension: string): string {
  return `${cacheDirectory}${ACCOUNT_FILE_PREFIX[kind]}${Date.now()}.${extension}`;
}

/** expo-print writes every PDF (chat exports) here, on iOS and Android alike. */
const PRINTED_PDF_DIRECTORY = "Print/";

/** A PDF named for the person (`Spanish verbs.pdf`), beside expo-print's own; sign-out clears both. */
export function namedPdfFile(name: string): string | null {
  return cacheDirectory ? fileUri(`${cacheDirectory}${PRINTED_PDF_DIRECTORY}`, name) : null;
}
/** expo-audio writes each voice recording here (iOS, Android): `recording-<id>.m4a`. */
const RECORDING_DIRECTORIES = ["ExpoAudio/", "Audio/"] as const;
const RECORDING_PREFIX = "recording-";

/**
 * The copy of each photo or file picked (expo-image-picker, expo-document-picker),
 * and each re-encode or crop (expo-image-manipulator: composer photos, scanner
 * crops, profile photos). Every file in them is one the person chose.
 */
const PICKER_COPY_DIRECTORIES = ["ImagePicker/", "DocumentPicker/", "ImageManipulator/"] as const;
/** A week: long past any pick a new run could still be handed. */
const PICKER_COPY_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

const PREFIXES: readonly string[] = Object.values(ACCOUNT_FILE_PREFIX);

async function filesIn(directory: string): Promise<string[]> {
  return readDirectoryAsync(directory).catch(() => [] as string[]);
}

async function pickerCopies(cache: string): Promise<string[]> {
  const directories = PICKER_COPY_DIRECTORIES.map((directory) => `${cache}${directory}`);
  const listed = await Promise.all(directories.map(filesIn));
  return listed.flatMap((names, index) => names.map((name) => fileUri(directories[index]!, name)));
}

/** Sign-out: delete every file above, so nothing of this account stays on the phone. */
export async function deleteAccountFiles(): Promise<void> {
  const cache = cacheDirectory;
  if (!cache) return;
  const pdfs = `${cache}${PRINTED_PDF_DIRECTORY}`;
  const recordingDirs = RECORDING_DIRECTORIES.map((directory) => `${cache}${directory}`);
  const [names, printed, picked, ...recordings] = await Promise.all([
    filesIn(cache), filesIn(pdfs), pickerCopies(cache), ...recordingDirs.map(filesIn),
  ]);
  const paths = [
    ...names.filter((name) => PREFIXES.some((prefix) => name.startsWith(prefix))).map((name) => fileUri(cache, name)),
    ...printed.filter((name) => name.toLowerCase().endsWith(".pdf")).map((name) => fileUri(pdfs, name)),
    ...picked,
    // A recording a crash or a kill left behind (each is deleted once sent, LEAK-04).
    ...recordings.flatMap((files, index) =>
      files.filter((name) => name.startsWith(RECORDING_PREFIX)).map((name) => fileUri(recordingDirs[index]!, name))),
  ];
  await Promise.allSettled(paths.map((path) => deleteAsync(path, { idempotent: true })));
}

/**
 * Once a run, before anything can be picked: delete picker copies older than a week.
 * A sent photo's copy draws its bubble (and its viewer) for as long as the chat is
 * open, so a send never deletes it; a new run holds none of them (the chat file
 * keeps no local preview). Read before any pick: a Files pick's copy keeps the
 * original's date on iOS, so a fresh one can look old.
 */
export async function sweepOldPickerCopies(now: number = Date.now()): Promise<void> {
  const cache = cacheDirectory;
  if (!cache) return;
  const copies = await pickerCopies(cache);
  const old = await Promise.all(copies.map(async (path) => {
    const info = await getInfoAsync(path).catch(() => null);
    // Legacy file info reports seconds.
    return info?.exists && now - (info.modificationTime ?? 0) * 1000 > PICKER_COPY_MAX_AGE_MS ? path : null;
  }));
  const stale = old.filter((path): path is string => path !== null);
  await Promise.allSettled(stale.map((path) => deleteAsync(path, { idempotent: true })));
}
