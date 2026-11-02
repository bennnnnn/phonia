/**
 * Structural guard: each feature owns its internals (code-health audit ARCH-10), as
 * the API's module-boundary tests hold for `modules/`.
 *
 * - A feature imports another feature only through that feature's public modules:
 *   its `api.ts` and `types.ts`, and what PUBLIC lists below. A module is public
 *   because another feature or a composition point uses it; one nobody outside its
 *   feature imports any more leaves the list.
 * - Shared code (components, contexts, hooks, lib, ui) imports a feature only from
 *   the composition points listed in SHARED_ENTRIES, and only its public modules.
 *   `ui/` never does. Routes (`app/`) compose features freely.
 * - Features depend on each other without a cycle.
 *
 * Each feature is imported by path, not through a barrel: Metro and jest evaluate a
 * barrel's every re-export, which pulled React Native into pure model tests. A change
 * one feature makes that another feature's cache follows is an event (`lib/appEvents.ts`),
 * not a call into the other feature's storage.
 */
import * as ts from "typescript";

declare const __dirname: string;

const ROOT = ts.sys.resolvePath(`${__dirname}/../..`);
const SHARED_DIRS = ["components", "contexts", "hooks", "lib", "ui"];

/** Feature → the modules (paths inside it) other features and composition points may import. */
const PUBLIC: Record<string, readonly string[]> = {
  account: ["components/settingsUi.tsx"],
  attachments: [
    "components/AttachmentSourceSheet.tsx",
    "components/ChatMessageImage.tsx",
    "components/ChatMessageImageStrip.tsx",
    "components/ChatMessagePdf.tsx",
    "components/ComposerAttachmentPreview.tsx",
    "hooks/useAttachmentIndexed.ts",
    "model/attachmentErrors.ts",
    "model/attachmentStatusFile.ts",
    "model/attachmentUri.ts",
    "model/attachments.ts",
    "model/downloadChatAttachment.ts",
    "model/galleryListCache.ts",
    "model/localAttachmentFile.ts",
    "model/pendingComposerAttachment.ts",
  ],
  auth: [],
  billing: ["components/UpgradeSheet.tsx", "model/purchases.ts"],
  chat: [
    "model/chatListCache.ts",
    "model/composerDraftReset.ts",
    "model/messageCache.ts",
    "model/quotaNudgeDismissal.ts",
    "model/streamingDraftStore.ts",
  ],
  drafts: [
    "components/EmailCard.tsx",
    "context/emailDraftPersist.tsx",
    "model/emailCompose.ts",
    "model/emailDraftFlush.ts",
    "model/emailDraftSanitize.ts",
  ],
  home: ["components/HomeStarters.tsx"],
  images: [
    "components/ImageGenPlaceholder.tsx",
    "hooks/useImageGeneration.ts",
    "model/imageGenMessages.ts",
    "model/imageGenTurn.ts",
    "model/imageIntentPrefilter.ts",
  ],
  memory: ["model/memoryListCache.ts"],
  notifications: [
    "model/notificationChannels.ts",
    "model/pushNotifications.ts",
    "model/pushRegistration.ts",
  ],
  scanner: [
    "components/LazyMathEquationScanner.tsx",
    "model/readBack.ts",
    "model/scanReadError.ts",
  ],
  search: ["components/DrawerSearchResults.tsx", "hooks/useDrawerSearch.ts"],
  speech: [
    "components/LiveTalkButton.tsx",
    "components/LiveTalkComposerControls.tsx",
    "components/LazyLiveTalkOverlay.tsx",
    "components/VoiceComposerWaveform.tsx",
    "components/VoiceMicButton.tsx",
    "hooks/useLiveTalk.ts",
    "hooks/useVoiceInput.ts",
    "model/liveTalkLogic.ts",
    "model/pronunciation.ts",
    "model/speechRate.ts",
    "model/ttsPreference.ts",
    "model/voices.ts",
  ],
  suggestions: ["components/RelatedPromptLines.tsx"],
  todos: [
    "components/ReminderProposalCard.tsx",
    "components/TodoLinkButton.tsx",
    "context/TodosContext.tsx",
    "hooks/useReminderBadgeCount.ts",
    "model/dueDate.ts",
    "model/homeReminderNudges.ts",
    "model/homeUrgentTodos.ts",
    "model/reminderFence.ts",
    "model/reminderProposal.ts",
    "model/reminderSeen.ts",
    "model/reminderTiming.ts",
    "model/todoLink.ts",
    "model/todoReminders.ts",
  ],
};

/** Shared files that compose features, and why. Shrink only: move the rest into a feature. */
const SHARED_ENTRIES: Record<string, string> = {
  "lib/api.ts": "the network barrel composes every feature's api slice",
  "lib/signOutCleanup.ts": "sign-out clears every feature's stores",
  "components/rich/RichFence.tsx": "renders each fence; the email fence is the drafts card",
  "lib/richBlocks.ts": "reads each rich block; an email draft is sanitized by drafts",
  "lib/markdown/assistantMessageContent.ts": "a reply's reminder card and To-do button are todos fences",
  "components/Avatar.tsx": "the profile photo is an attachment",
  "contexts/AuthContext.tsx": "a sign-out takes the device's push token with it (notifications)",
  "hooks/useBootstrapSync.ts": "a signed-in launch starts billing and push sync",
};

type Edge = { from: string; to: string };

function sourceFiles(): string[] {
  return ["app", "features", ...SHARED_DIRS]
    .flatMap((dir) =>
      ts.sys.readDirectory(`${ROOT}/${dir}`, [".ts", ".tsx"], ["**/__tests__/**", "**/vendor/**"]),
    )
    .filter((file) => !file.endsWith(".d.ts"));
}

function importEdges(files: string[]): Edge[] {
  const { config } = ts.readConfigFile(`${ROOT}/tsconfig.json`, ts.sys.readFile);
  const options = ts.parseJsonConfigFileContent(config, ts.sys, ROOT).options;
  const cache = ts.createModuleResolutionCache(ROOT, (name) => name, options);
  const known = new Set(files);
  const edges: Edge[] = [];
  for (const file of files) {
    const { importedFiles } = ts.preProcessFile(ts.sys.readFile(file) ?? "", true, true);
    for (const { fileName } of importedFiles) {
      const target = ts.resolveModuleName(fileName, file, options, ts.sys, cache).resolvedModule
        ?.resolvedFileName;
      if (target && known.has(target)) {
        edges.push({ from: file.slice(ROOT.length + 1), to: target.slice(ROOT.length + 1) });
      }
    }
  }
  return edges;
}

/** `features/<name>/<rest>` → `[name, rest]`; null outside features. */
function featurePath(path: string): [string, string] | null {
  const match = /^features\/([^/]+)\/(.+)$/.exec(path);
  return match ? [match[1]!, match[2]!] : null;
}

function isPublic(path: string): boolean {
  const [feature, rest] = featurePath(path) ?? ["", ""];
  return rest === "api.ts" || rest === "types.ts" || (PUBLIC[feature] ?? []).includes(rest);
}

/** Features in a dependency cycle, each cycle sorted. */
function featureCycles(graph: Map<string, Set<string>>): string[][] {
  const index = new Map<string, number>();
  const low = new Map<string, number>();
  const stack: string[] = [];
  const onStack = new Set<string>();
  const cycles: string[][] = [];
  const visit = (node: string): void => {
    index.set(node, index.size);
    low.set(node, index.get(node) ?? 0);
    stack.push(node);
    onStack.add(node);
    for (const next of graph.get(node) ?? []) {
      if (!index.has(next)) visit(next);
      if (onStack.has(next)) low.set(node, Math.min(low.get(node) ?? 0, low.get(next) ?? 0));
    }
    if (low.get(node) !== index.get(node)) return;
    const members: string[] = [];
    let member: string | undefined;
    do {
      member = stack.pop();
      if (member === undefined) break;
      onStack.delete(member);
      members.push(member);
    } while (member !== node);
    if (members.length > 1) cycles.push(members.sort());
  };
  for (const node of graph.keys()) if (!index.has(node)) visit(node);
  return cycles;
}

describe("feature boundaries", () => {
  const edges = importEdges(sourceFiles());
  const features = new Set(
    edges.flatMap(({ from, to }) => [featurePath(from)?.[0], featurePath(to)?.[0]]).filter(Boolean),
  );

  it("knows every feature and resolves @/ imports", () => {
    expect([...features].sort()).toEqual(Object.keys(PUBLIC).sort());
    expect(edges).toContainEqual({ from: "lib/api.ts", to: "features/chat/api.ts" });
  });

  it("imports another feature only through its public modules", () => {
    const reaches = edges
      .filter(({ from, to }) => {
        const source = featurePath(from)?.[0];
        const target = featurePath(to)?.[0];
        return source && target && source !== target && !isPublic(to);
      })
      .map(({ from, to }) => `${from} -> ${to}`);
    expect(reaches).toEqual([]);
  });

  it("lets shared code reach features only at its composition points", () => {
    const reaches = edges
      .filter(({ from, to }) => SHARED_DIRS.includes(from.split("/")[0]!) && featurePath(to))
      .filter(({ from, to }) => !(from in SHARED_ENTRIES) || !isPublic(to))
      .map(({ from, to }) => `${from} -> ${to}`);
    expect(reaches).toEqual([]);
  });

  it("keeps features free of dependency cycles", () => {
    const graph = new Map<string, Set<string>>();
    for (const { from, to } of edges) {
      const source = featurePath(from)?.[0];
      const target = featurePath(to)?.[0];
      if (!source || !target || source === target) continue;
      graph.set(source, (graph.get(source) ?? new Set()).add(target));
    }
    expect(featureCycles(graph)).toEqual([]);
  });

  it("lists only what is still used: public modules and composition points", () => {
    const usedFromOutside = new Set(
      edges
        .filter(({ from, to }) => featurePath(to) && featurePath(from)?.[0] !== featurePath(to)?.[0])
        .filter(({ from }) => !from.startsWith("app/"))
        .map(({ to }) => to),
    );
    const unusedPublic = Object.entries(PUBLIC).flatMap(([feature, modules]) =>
      modules.map((module) => `features/${feature}/${module}`).filter((path) => !usedFromOutside.has(path)),
    );
    const composing = new Set(edges.filter(({ to }) => featurePath(to)).map(({ from }) => from));
    const staleEntries = Object.keys(SHARED_ENTRIES).filter((file) => !composing.has(file));
    expect({ unusedPublic, staleEntries }).toEqual({ unusedPublic: [], staleEntries: [] });
  });

  it("finds a cycle when there is one", () => {
    const sample = new Map([
      ["a", new Set(["b"])],
      ["b", new Set(["a"])],
      ["c", new Set(["a"])],
    ]);
    expect(featureCycles(sample)).toEqual([["a", "b"]]);
  });
});
