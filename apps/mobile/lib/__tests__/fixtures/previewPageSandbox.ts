/**
 * Runs a preview page's own scripts and a block's config script against fake
 * browser globals, so a test sees what the page does with the data a WebView
 * hands it (lib/preview/previewPage.ts) without a browser.
 */
import { previewPageConfigScript, type PreviewPageConfig } from "@/lib/preview/previewPage";

type FakeElement = { textContent: string; style: Record<string, string> };
type Listener = (event: unknown) => void;

/** A tap's (or a script's) click on `target`, as the page's listeners see it. */
export type FakeClick = { target: unknown; isTrusted: boolean; defaultPrevented: boolean };

/** An `<a>` in the page; `inSvg` spells it as SVG does, with an xlink:href. */
export function fakeAnchor(href: string, { inSvg = false } = {}) {
  return {
    nodeName: inSvg ? "a" : "A",
    parentNode: null,
    getAttribute: (name: string) => (name === "href" && !inSvg ? href : null),
    getAttributeNS: (_namespace: string, name: string) => (name === "href" && inSvg ? href : null),
  };
}

/**
 * The bodies of a page's bare `<script>` blocks, in order, whatever their case. A tag with
 * attributes never runs here: `<script src>` loads a library the test stands in for, and
 * `<script type="text/pdf-worker">` holds the PDF worker's source as data.
 */
function inlineScripts(html: string): string[] {
  const lower = html.toLowerCase();
  const open = "<script>";
  const close = "</script>";
  const bodies: string[] = [];
  let start = lower.indexOf(open);
  while (start >= 0) {
    const end = lower.indexOf(close, start + open.length);
    if (end < 0) break;
    bodies.push(html.slice(start + open.length, end));
    start = lower.indexOf(open, end + close.length);
  }
  return bodies;
}

export function previewPageSandbox(globals: Record<string, unknown> = {}) {
  const posted: unknown[] = [];
  const css: Record<string, string> = {};
  const elements: Record<string, FakeElement> = {};
  const frames: (() => void)[] = [];
  const windowListeners: Record<string, Listener[]> = {};
  const clickListeners: Listener[] = [];
  const window: Record<string, unknown> & {
    addEventListener: (type: string, listener: Listener) => void;
  } = {
    ReactNativeWebView: { postMessage: (data: string) => posted.push(JSON.parse(data)) },
    addEventListener: (type: string, listener: Listener) => {
      (windowListeners[type] ??= []).push(listener);
    },
  };
  const document = {
    baseURI: "file:///cache/preview-pages/page-0123456789abcdef.html",
    documentElement: {
      style: {
        setProperty: (name: string, value: string) => {
          css[name] = value;
        },
      },
    },
    addEventListener: (type: string, listener: Listener) => {
      if (type === "click") clickListeners.push(listener);
    },
    getElementById: (id: string) => (elements[id] ??= { textContent: "", style: {} }),
    querySelector: () => null,
    body: { scrollHeight: 100 },
  };
  const scope: Record<string, unknown> = {
    window,
    document,
    requestAnimationFrame: (frame: () => void) => frames.push(frame),
    ...globals,
  };
  const run = (source: string) => new Function(...Object.keys(scope), source)(...Object.values(scope));

  return {
    window,
    document,
    /** What the page posted to the app, parsed. */
    posted,
    /** CSS variables the page set on its root. */
    css,
    elements,
    /** The page's inline scripts in order (a library under test is a stand-in). */
    loadPage(html: string) {
      for (const source of inlineScripts(html)) run(source);
    },
    /** What the WebView injects for one block. */
    hand(config: PreviewPageConfig) {
      run(previewPageConfigScript(config));
    },
    fire(type: string) {
      for (const listener of windowListeners[type] ?? []) listener({ type });
    },
    click(target: unknown, { isTrusted = true } = {}): FakeClick {
      const click: FakeClick = { target, isTrusted, defaultPrevented: false };
      const event = {
        ...click,
        preventDefault: () => {
          click.defaultPrevented = true;
        },
        stopPropagation: () => undefined,
      };
      for (const listener of clickListeners) listener(event);
      return click;
    },
    runFrames() {
      frames.splice(0).forEach((frame) => frame());
    },
  };
}

/** Lets the page's promise callbacks run. */
export function settle(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}
