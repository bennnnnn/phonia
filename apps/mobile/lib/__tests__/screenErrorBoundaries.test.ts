/**
 * Structural guard: a screen that throws while it renders shows the shared error
 * view (`components/ScreenErrorBoundary.tsx`), translated and reported, wherever
 * it is. Expo Router draws the `ErrorBoundary` of the nearest route file that
 * exports one: the route's own, else its section's stack layout, else the root
 * layout's, which stands in for the whole app.
 *
 * Routes stay one-line adapters (apps/api architecture tests hold them so), so a
 * route's own boundary comes from the screen module it re-exports it from
 * (`export { default, ErrorBoundary } from "@/…Screen";`), and Settings and Memory
 * take theirs from their stack layout (a crash on any of its pages). A new screen
 * route gets one of those unless it is listed here, with a reason, as one only
 * the root's catches.
 */
import { appFiles, readSource, relative, ROOT } from "@/lib/__tests__/support/sourceFiles";

const ROOT_LAYOUT = "app/_layout.tsx";
const EXPORT =
  'export { ScreenErrorBoundary as ErrorBoundary } from "@/components/ScreenErrorBoundary";';
const ROUTE_WITH_BOUNDARY = /^export \{ default, ErrorBoundary \} from "@\/(.+)";$/;
/** Any `ErrorBoundary` a file exports: the shared view, the router's default or its own. */
const ANY_BOUNDARY = /^export (?:\{[^}]*\bErrorBoundary\b[^}]*\}|(?:function|const|class) ErrorBoundary\b)/m;

/** Routes only the root's boundary catches, and why. */
const ROOT_CATCHES = new Map([
  ["app/index.tsx", "the chat: each message and each block in it has its own boundary"],
  ["app/login.tsx", "the sign-in flow, before any account screen"],
  ["app/onboarding.tsx", "the sign-in flow, before any account screen"],
  ["app/consent.tsx", "the sign-in flow, before any account screen"],
  ["app/+not-found.tsx", "draws only a link home"],
]);

const SOURCES = new Set(appFiles().map(relative));
const APP_FILES = [...SOURCES].filter((path) => path.startsWith("app/"));
const ROUTES = APP_FILES.filter((path) => !/\/_layout\.tsx$/.test(path));

function text(path: string): string {
  return readSource(`${ROOT}/${path}`);
}

function exportsBoundary(path: string): boolean {
  return SOURCES.has(path) && ANY_BOUNDARY.test(text(path));
}

/** The file whose `ErrorBoundary` Expo Router draws for a crash in `file`. */
function nearestBoundary(file: string): string | null {
  if (exportsBoundary(file)) return file;
  const folders = file.split("/").slice(0, -1);
  for (let depth = folders.length; depth > 0; depth -= 1) {
    const layout = `${folders.slice(0, depth).join("/")}/_layout.tsx`;
    if (exportsBoundary(layout)) return layout;
  }
  return null;
}

/** It exports the shared view, or re-exports the one its screen module exports. */
function drawsSharedView(file: string): boolean {
  const source = text(file);
  if (source.includes(EXPORT)) return true;
  const screen = ROUTE_WITH_BOUNDARY.exec(source.trim())?.[1];
  return screen !== undefined && SOURCES.has(`${screen}.tsx`) && text(`${screen}.tsx`).includes(EXPORT);
}

describe("screen routes", () => {
  it("finds the route files", () => {
    expect(ROUTES).toEqual(
      expect.arrayContaining(["app/index.tsx", "app/todos.tsx", "app/settings/profile.tsx"]),
    );
  });

  it("are each caught by the shared error view at their nearest boundary", () => {
    // Layouts too: a layout's own boundary, or the one above it, catches its crash.
    const uncovered = APP_FILES.flatMap((file) => {
      const boundary = nearestBoundary(file);
      return boundary !== null && drawsSharedView(boundary) ? [] : [`${file} → ${boundary}`];
    });
    expect(uncovered).toEqual([]);
  });

  it("each have their own or their section's, unless listed", () => {
    const toRoot = ROUTES.filter(
      (path) => !ROOT_CATCHES.has(path) && nearestBoundary(path) === ROOT_LAYOUT,
    );
    expect(toRoot).toEqual([]);
  });

  it("lists only routes that exist and that only the root's catches", () => {
    const stale = [...ROOT_CATCHES.keys()].filter(
      (path) => !ROUTES.includes(path) || nearestBoundary(path) !== ROOT_LAYOUT,
    );
    expect(stale).toEqual([]);
  });
});
