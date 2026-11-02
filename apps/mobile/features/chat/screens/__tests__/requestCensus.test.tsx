/**
 * @jest-environment ./jest.timeZoneEnvironment.js
 */
/**
 * Request census: every request the phone sends through its one network boundary
 * (`fetch`, which only lib/api/client.ts calls for our API) and every socket it
 * opens, along an everyday session: cold start, chats opened, a turn, the drawer,
 * each screen, returns from the background, an expired token, a relaunch. Real
 * providers, hooks and caches; the server, the device stores and expo-router are
 * stand-ins. Each step has a ceiling: a step that sends more fails here.
 * `CENSUS=1 npx jest requestCensus` prints the requests.
 */
import type { ReactNode } from "react";

declare const setTestTimeZone: (zone: string) => void;

class MockExpoEmitter {
  addListener() { return { remove: () => {} }; }
  removeListener() {}
  removeAllListeners() {}
  emit() {}
  listenerCount() { return 0; }
}
(globalThis as unknown as { expo: unknown }).expo = {
  EventEmitter: MockExpoEmitter,
  NativeModule: MockExpoEmitter,
  SharedObject: MockExpoEmitter,
  SharedRef: MockExpoEmitter,
  modules: {},
  uuidv4: () => "uuid",
  uuidv5: () => "uuid",
  getViewConfig: () => null,
  reloadAppAsync: async () => {},
};

/** A native module stand-in: every member is a callable resolving to nothing; nothing is thenable. */
function mockNativeModule(name: string): unknown {
  const call = () => Promise.resolve(undefined);
  return new Proxy(call, {
    get(_target, prop) {
      if (prop === "then") return undefined;
      if (prop === "__esModule") return true;
      if (prop === Symbol.toPrimitive || prop === "toString") return () => name;
      return mockNativeModule(`${name}.${String(prop)}`);
    },
    apply: () => Promise.resolve(undefined),
    construct: () => mockNativeModule(`new ${name}`) as object,
  });
}

type Logged = { method: string; path: string; status: number; at: number };
const mockLog: Logged[] = [];
const mockSecure = new Map<string, string>();
const mockFiles = new Map<string, string>();
let mockParams: Record<string, string | undefined> = {};
const mockRouter = {
  push: jest.fn((href: unknown) => mockRouteTo(href)),
  replace: jest.fn((href: unknown) => mockRouteTo(href)),
  setParams: jest.fn((p: Record<string, string | undefined>) => {
    mockParams = { ...mockParams, ...p };
    setTimeout(() => void mockRerender?.(), 0);
  }),
  back: jest.fn(),
  canGoBack: () => true,
  dismissTo: jest.fn(),
  navigate: jest.fn((href: unknown) => mockRouteTo(href)),
};
let mockRerender: (() => Promise<void> | void) | null = null;
/** A move to the chat screen (the root route) sets its params; another route leaves them. */
function mockRouteTo(href: unknown) {
  setTimeout(() => void mockRerender?.(), 0);
  if (typeof href === "object" && href && "pathname" in href && href.pathname === "/") {
    mockParams = { ...(href as { params?: Record<string, string> }).params };
  } else if (typeof href === "string" && (href === "/" || href.startsWith("/?"))) {
    mockParams = Object.fromEntries(new URLSearchParams(href.slice(2)));
  }
}

jest.mock("expo-router", () => {
  const React = jest.requireActual("react");
  // The screen on top has focus: the chat screen loses it while another is pushed over it.
  const Focus = React.createContext(true);
  return {
    MockFocus: Focus.Provider,
    Redirect: () => null,
    Stack: Object.assign(({ children }: { children?: ReactNode }) => children ?? null, {
      Screen: () => null,
    }),
    useRouter: () => mockRouter,
    useNavigation: () => ({ setOptions: jest.fn(), addListener: () => () => {}, isFocused: () => true }),
    useLocalSearchParams: () => mockParams,
    useGlobalSearchParams: () => mockParams,
    usePathname: () => "/",
    useSegments: () => [],
    useFocusEffect: (effect: () => void | (() => void)) => {
      const focused = React.useContext(Focus);
      React.useEffect(() => (focused ? effect() : undefined), [effect, focused]);
    },
    Link: ({ children }: { children?: ReactNode }) => children ?? null,
  };
});

jest.mock("expo-modules-core", () => {
  class EventEmitter { addListener() { return { remove: () => {} }; } removeAllListeners() {} emit() {} }
  const native = new Proxy({}, { get: (_t, k) => (k === "then" ? undefined : () => undefined) });
  return {
    EventEmitter,
    NativeModule: class {},
    SharedObject: class {},
    SharedRef: class {},
    // expo-localization: the OS's clock-change event, which a test sends for a new zone.
    requireOptionalNativeModule: (name: string) => name === "ExpoLocalization" ? {
      getCalendars: () => [],
      addListener: (_event: string, listener: () => void) => {
        mockClockListeners.add(listener);
        return { remove: () => { mockClockListeners.delete(listener); } };
      },
    } : null,
    requireNativeModule: () => native,
    requireNativeViewManager: () => () => null,
    registerWebModule: (m: unknown) => m,
    Platform: { OS: "ios" },
    PermissionStatus: { GRANTED: "granted", DENIED: "denied", UNDETERMINED: "undetermined" },
    createPermissionHook: () => () => [null, async () => ({}), async () => ({})],
    CodedError: class extends Error {},
    UnavailabilityError: class extends Error {},
    uuid: { v4: () => "uuid" },
  };
});

const mockClockListeners = new Set<() => void>();

const mockNetState = { type: "wifi", isConnected: true, isInternetReachable: true, details: { ipAddress: "10.0.0.2" } };
/** NetInfo's subscribers: a test can move the phone to another network. */
const mockNetListeners = new Set<(s: unknown) => void>();
jest.mock("@react-native-community/netinfo", () => ({
  __esModule: true,
  default: {
    configure: () => {},
    fetch: async () => mockNetState,
    refresh: async () => mockNetState,
    addEventListener: (listener: (s: unknown) => void) => {
      mockNetListeners.add(listener);
      void Promise.resolve().then(() => listener(mockNetState));
      return () => { mockNetListeners.delete(listener); };
    },
  },
}));

jest.mock("expo-media-library", () => mockNativeModule("expo-media-library"));
jest.mock("expo-image-picker", () => mockNativeModule("expo-image-picker"));
jest.mock("expo-document-picker", () => mockNativeModule("expo-document-picker"));
jest.mock("expo-audio", () => mockNativeModule("expo-audio"));
jest.mock("expo-speech", () => mockNativeModule("expo-speech"));
jest.mock("expo-location", () => mockNativeModule("expo-location"));
jest.mock("expo-sharing", () => mockNativeModule("expo-sharing"));
jest.mock("expo-print", () => mockNativeModule("expo-print"));
jest.mock("expo-web-browser", () => mockNativeModule("expo-web-browser"));
jest.mock("expo-linking", () => mockNativeModule("expo-linking"));
jest.mock("expo-device", () => mockNativeModule("expo-device"));
jest.mock("expo-apple-authentication", () => mockNativeModule("expo-apple-authentication"));
jest.mock("@react-native-google-signin/google-signin", () => mockNativeModule("@react-native-google-signin/google-signin"));
jest.mock("react-native-purchases", () => mockNativeModule("react-native-purchases"));
jest.mock("react-native-webview", () => mockNativeModule("react-native-webview"));
jest.mock("expo-image-manipulator", () => mockNativeModule("expo-image-manipulator"));
jest.mock("expo-splash-screen", () => mockNativeModule("expo-splash-screen"));
jest.mock("expo-font", () => mockNativeModule("expo-font"));
jest.mock("expo-updates", () => mockNativeModule("expo-updates"));
jest.mock("react-native-webrtc", () => mockNativeModule("react-native-webrtc"));
jest.mock("react-native-vision-camera", () => mockNativeModule("react-native-vision-camera"));
jest.mock("react-native-vision-camera-mlkit", () => mockNativeModule("react-native-vision-camera-mlkit"));
jest.mock("react-native-vision-camera-worklets", () => mockNativeModule("react-native-vision-camera-worklets"));
jest.mock("react-native-nitro-image", () => mockNativeModule("react-native-nitro-image"));
jest.mock("react-native-nitro-modules", () => mockNativeModule("react-native-nitro-modules"));
jest.mock("@sentry/react-native", () => mockNativeModule("@sentry/react-native"));
jest.mock("@expo/dom-webview", () => mockNativeModule("@expo/dom-webview"));

jest.mock("react-native-gesture-handler/ReanimatedSwipeable", () => {
  const { View } = jest.requireActual("react-native");
  return { __esModule: true, default: View };
});

jest.mock("expo-constants", () => ({
  __esModule: true,
  default: {
    executionEnvironment: "standalone",
    appOwnership: null,
    expoConfig: { extra: { eas: { projectId: "proj" } }, version: "1.0.0" },
  },
  ExecutionEnvironment: { Bare: "bare", Standalone: "standalone", StoreClient: "storeClient" },
}));

jest.mock("expo-secure-store", () => ({
  getItemAsync: async (key: string) => mockSecure.get(key) ?? null,
  setItemAsync: async (key: string, value: string) => { mockSecure.set(key, value); },
  deleteItemAsync: async (key: string) => { mockSecure.delete(key); },
  AFTER_FIRST_UNLOCK: 0,
  AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY: 0,
}));

jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  documentDirectory: "file:///doc/",
  getInfoAsync: async (path: string) => ({ exists: mockFiles.has(path) }),
  readAsStringAsync: async (path: string) => {
    const v = mockFiles.get(path);
    if (v === undefined) throw new Error("missing");
    return v;
  },
  writeAsStringAsync: async (path: string, value: string) => { mockFiles.set(path, value); },
  deleteAsync: async (path: string) => { mockFiles.delete(path); },
  makeDirectoryAsync: async () => {},
  readDirectoryAsync: async () => [],
  copyAsync: async () => {},
  moveAsync: async () => {},
  EncodingType: { UTF8: "utf8", Base64: "base64" },
}));

jest.mock("expo-file-system", () => ({
  File: class { exists = false; textSync() { return ""; } },
  Paths: { document: "doc", cache: "cache" },
  Directory: class {},
}));

jest.mock("expo-notifications", () => ({
  getPermissionsAsync: async () => ({ status: "granted" }),
  requestPermissionsAsync: async () => ({ status: "granted" }),
  getExpoPushTokenAsync: async () => ({ data: "ExponentPushToken[abc]" }),
  getDevicePushTokenAsync: async () => ({ data: "apns-token", type: "ios" }),
  getLastNotificationResponseAsync: async () => null,
  addNotificationResponseReceivedListener: () => ({ remove: () => {} }),
  addNotificationReceivedListener: () => ({ remove: () => {} }),
  setNotificationHandler: () => {},
  getAllScheduledNotificationsAsync: async () => [],
  scheduleNotificationAsync: async () => "id",
  cancelScheduledNotificationAsync: async () => {},
  setNotificationChannelAsync: async () => {},
  AndroidImportance: { HIGH: 4, DEFAULT: 3 },
  SchedulableTriggerInputTypes: { DATE: "date" },
}));

const USER_ID = "u1";
const NOW = "2026-10-24T12:00:00Z";
const NOW_S = Date.parse(NOW) / 1000;
const accessToken = (exp: number, n = 0) => `h.${btoa(JSON.stringify({ sub: USER_ID, exp, n }))}.s`;
/** The zone the phone names now. */
const deviceZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone;
const HOME_ZONE = deviceZone();
const USER = {
  id: USER_ID, email: "a@b.c", name: "Ann", avatar_url: null, default_model: "auto", plan: "free",
  features: [], enabled_models: null, ai_data_consent_at: NOW, response_tone: "", memory_enabled: true,
  push_notifications_enabled: true, push_reminders_enabled: true, reminder_lead_minutes: 0, locale: "en",
  // The device's own zone (lib/deviceTimezone): a profile in another is patched on start.
  timezone: HOME_ZONE, location: null, location_enabled: false, custom_instructions: null, age: null,
  country: null, job: null, created_at: NOW,
};
const uuid = (kind: number, n: number) => `00000000-0000-4000-8${kind}00-${String(n).padStart(12, "0")}`;
const chatId = (n: number) => uuid(1, n);
const CHATS = Array.from({ length: 30 }, (_, i) => ({
  id: chatId(i), title: `Chat ${i}`, model: "auto", pinned: false, archived: false, created_at: NOW, updated_at: NOW,
}));
const fileContent = (n: number, type: string) =>
  `Summarize this file.\n[File: /attachments/${uuid(4, n)}/file]\n[File (${type})]`;
const MESSAGES = Array.from({ length: 30 }, (_, i) => ({
  id: uuid(2, i),
  role: i % 2 ? "assistant" : "user",
  // Three of the user's messages carry a file: two documents and a PDF.
  content: i === 4 ? fileContent(1, "text/plain") : i === 10 ? fileContent(2, "text/csv")
    : i === 16 ? fileContent(3, "application/pdf") : `Message ${i}`,
  model: null,
  created_at: NOW,
}));

/** A turn the server finished after its socket dropped: on the chat's page once saved. */
let savedTurn: object[] = [];

/** A new chat's title lands after this many reads of it (the topic job runs after the reply). */
const TITLE_AFTER_READS = 2;
const titleReads = new Map<string, number>();
let refreshes = 0;
let created = 0;

/** The profile's zone on the server: a PATCH of /auth/me moves it. */
let profileZone = HOME_ZONE;

function serverBody(method: string, path: string, body?: string): unknown {
  const p = path.split("?")[0];
  if (p === "/auth/me" && method === "PATCH") {
    const patch = JSON.parse(body ?? "{}") as { timezone?: string };
    if (patch.timezone) profileZone = patch.timezone;
  }
  if (p === "/auth/me") return { ...USER, timezone: profileZone };
  if (p === "/auth/refresh") {
    refreshes += 1;
    return {
      access_token: accessToken(Math.floor(Date.now() / 1000) + 3600, refreshes),
      refresh_token: `r${refreshes}`,
      user: { ...USER, timezone: profileZone },
    };
  }
  if (p === "/models") return [{ id: "free-chat", label: "Free", available: true, plan_access: "free" }];
  if (p === "/todos/page") return { items: [], next_cursor: null };
  if (p === "/chats/usage/today") return { date: "2026-10-24", tokens_used: 0, daily_limit: 100000 };
  if (p === "/chats" && method === "POST") {
    created += 1;
    return { ...CHATS[0], id: chatId(100 + created), title: null };
  }
  if (p === "/chats") {
    return {
      pinned: [], today: CHATS, yesterday: [], last_7_days: [], this_month: [], older: [], archived: [],
      next_cursor: null, archived_next_cursor: null,
    };
  }
  if (/^\/chats\/[^/]+\/messages$/.test(p)) return { messages: [...MESSAGES, ...savedTurn], has_more: false };
  if (/^\/chats\/[^/]+$/.test(p)) {
    const id = p.split("/")[2];
    const reads = (titleReads.get(id) ?? 0) + 1;
    titleReads.set(id, reads);
    return { ...CHATS[0], id, title: reads > TITLE_AFTER_READS ? "A new question" : null };
  }
  if (p === "/memories/documents") return { documents: [], scanning: false };
  if (p === "/memories") return [];
  if (p === "/attachments") return { items: [], next_cursor: null };
  if (p === "/auth/sessions") return { sessions: [] };
  if (/^\/attachments\/[^/]+\/url$/.test(p)) {
    return {
      id: p.split("/")[2], content_type: "text/plain", size_bytes: 100, url: "x", indexed: true,
      original_filename: "notes.txt", created_at: "2026-01-01T00:00:00Z",
    };
  }
  return {};
}

/** The reads the server answers with an ETag (`core/etag.py`): the drawer, to-dos, a chat's newest
 * page, memory's pages and the signed-in devices. */
function revalidated(method: string, path: string): boolean {
  const p = path.split("?")[0];
  return method === "GET" && (
    (p === "/chats" && !/[?&]cursor=/.test(path)) || p === "/todos/page" || p === "/memories/documents" ||
    p === "/auth/sessions" ||
    (/^\/chats\/[^/]+\/messages$/.test(p) && !/[?&](before|after|around)=/.test(path))
  );
}

type FakeSocket = {
  sent: string[];
  closed: boolean;
  onmessage: ((event: { data: string }) => void) | null;
  drop: (code: number) => void;
};

let replies = 0;
/** The next reply's `done` says it changed the to-do list. */
let nextReplyChangesTodos = false;

function serverFrame(socket: FakeSocket, frame: object): void {
  if (!socket.closed) socket.onmessage?.({ data: JSON.stringify(frame) });
}

/** The server's side of a socket: a pong for a ping, and a streamed reply for a message. */
function answerFrame(socket: FakeSocket, raw: string): void {
  if (redisDown()) {
    // Redis down (`ws_api._close_while_down`): any frame is answered `unavailable`, then 1013.
    setTimeout(() => {
      serverFrame(socket, { type: "error", code: "unavailable", message: "Down", user_message_saved: false });
      socket.drop(1013);
    }, 5);
    return;
  }
  const frame = JSON.parse(raw) as { type?: string };
  if (frame.type === "ping") {
    setTimeout(() => serverFrame(socket, { type: "pong" }), 5);
    return;
  }
  if (frame.type !== "message") return;
  replies += 1;
  const id = uuid(3, replies);
  const todosChanged = nextReplyChangesTodos;
  nextReplyChangesTodos = false;
  setTimeout(() => serverFrame(socket, { type: "start" }), 50);
  for (let i = 0; i < 20; i++) {
    setTimeout(() => serverFrame(socket, { type: "token", content: `word${i} ` }), 100 + i * 20);
  }
  setTimeout(() => serverFrame(socket, { type: "stream_end" }), 600);
  setTimeout(() => serverFrame(socket, {
    type: "done", message_id: id, todos_changed: todosChanged,
    usage: { used_tokens: 10, daily_limit: 100000 },
  }), 700);
  setTimeout(() => serverFrame(socket, { type: "related_prompts", message_id: id, prompts: ["a?", "b?"] }), 900);
}

const mockAppStateListeners = new Set<(state: string) => void>();
const realFetch = globalThis.fetch;
const realWebSocket = globalThis.WebSocket;

/**
 * The API out: refusing connections, or answering every request with `status`. `live`: a
 * dependency is down behind a process that answers, so liveness (/health) still answers 200.
 * `code`: the API's own body names it (core/unavailable.py), where a gateway's names none.
 */
type Outage = "down" | { status: number; retryAfter: string; live?: boolean; code?: string };
/** The connection check's request (lib/api/connectivity.ts). */
const CHECK = "/health/dependencies";
let outage: Outage | null = null;
/** Redis down: the API answers, with its own `unavailable` (core/unavailable.py), sockets too. */
const redisDown = () => outage !== null && outage !== "down" && outage.code === "unavailable";
/** When the server closed or refused each socket. */
const socketDrops: number[] = [];
/** Sockets open now: a restart closes them all. */
const openSockets = new Set<{ drop: (code: number) => void }>();

/** Every open socket closes with `code`. */
function dropSockets(code: number): void {
  for (const socket of [...openSockets]) socket.drop(code);
  openSockets.clear();
}

/** A deploy: every open socket closes with uvicorn's 1012. */
function restartServer(): void {
  dropSockets(1012);
}

function installServer(): void {
  globalThis.fetch = jest.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const path = String(url).replace(/^https?:\/\/[^/]+/, "");
    const method = (init?.method ?? "GET").toUpperCase();
    // The connection check asks Google only when the API failed: the internet is up.
    if (String(url).includes("generate_204")) {
      mockLog.push({ method, path: "google/generate_204", status: 204, at: Date.now() });
      return new Response(null, { status: 204 });
    }
    if (outage === "down") {
      mockLog.push({ method, path, status: 0, at: Date.now() });
      throw new TypeError("Network request failed");
    }
    if (outage && !(outage.live && path === "/health")) {
      mockLog.push({ method, path, status: outage.status, at: Date.now() });
      const message = "Service temporarily unavailable. Please retry shortly.";
      const detail = outage.code ? { code: outage.code, message } : message;
      return new Response(JSON.stringify({ detail }), {
        status: outage.status,
        headers: { "content-type": "application/json", "retry-after": outage.retryAfter },
      });
    }
    const body = JSON.stringify(serverBody(method, path, typeof init?.body === "string" ? init.body : undefined));
    const etag = revalidated(method, path) ? `W/"${body.length}:${body.slice(-24)}"` : null;
    const headers = new Headers(init?.headers);
    if (etag && headers.get("If-None-Match") === etag) {
      mockLog.push({ method, path, status: 304, at: Date.now() });
      return new Response(null, { status: 304, headers: { etag } });
    }
    mockLog.push({ method, path, status: 200, at: Date.now() });
    return new Response(body, {
      status: 200,
      headers: { "content-type": "application/json", ...(etag ? { etag } : {}) },
    });
  }) as typeof fetch;
  class ServerSocket {
    readyState = 0;
    onopen: (() => void) | null = null;
    onmessage: ((event: { data: string }) => void) | null = null;
    onclose: ((event: { code: number }) => void) | null = null;
    onerror: (() => void) | null = null;
    sent: string[] = [];
    closed = false;
    constructor(url: string) {
      const refused = outage !== null && !redisDown();
      mockLog.push({ method: "WS", path: url.replace(/^wss?:\/\/[^/]+/, ""), status: refused ? 0 : 101, at: Date.now() });
      const handle = { drop: (code: number) => this.drop(code) };
      setTimeout(() => {
        if (this.closed) return;
        if (refused) {
          this.onerror?.();
          if (this.closed) socketDrops.push(Date.now());
          else this.drop(1006);
          return;
        }
        this.readyState = 1;
        openSockets.add(handle);
        this.onopen?.();
      }, 20);
    }
    drop(code: number) {
      if (this.closed) return;
      this.close();
      socketDrops.push(Date.now());
      this.onclose?.({ code });
    }
    send(data: string) {
      this.sent.push(data);
      answerFrame(this, data);
    }
    close() {
      this.closed = true;
      this.readyState = 3;
    }
  }
  globalThis.WebSocket = ServerSocket as unknown as typeof WebSocket;
}

afterAll(() => {
  globalThis.fetch = realFetch;
  globalThis.WebSocket = realWebSocket;
});

type Step = { title: string; requests: string[]; sent: Logged[] };
const steps: Step[] = [];
let mark = 0;
function step(title: string): void {
  const sent = mockLog.slice(mark);
  steps.push({
    title,
    sent,
    requests: sent.map((r) => `${r.method} ${r.path}${
      r.status === 304 || r.status >= 400 ? ` (${r.status})` : r.status === 0 ? " (refused)" : ""}`),
  });
  mark = mockLog.length;
}

/** Each change of the connection status the banner shows, and when. */
const statusChanges: { status: string; at: number }[] = [];

type Rtl = typeof import("@testing-library/react-native");
let rtl: Rtl;

/** Let `ms` pass on the fake clock, 50 ms at a time, with React's work flushed between. */
async function settle(ms = 50): Promise<void> {
  for (let elapsed = 0; elapsed < ms; elapsed += 50) {
    await rtl.act(async () => { await jest.advanceTimersByTimeAsync(50); });
  }
}

async function appState(state: "active" | "background" | "inactive"): Promise<void> {
  await rtl.act(async () => {
    for (const listener of [...mockAppStateListeners]) listener(state);
  });
}

type App = {
  ui: Awaited<ReturnType<Rtl["render"]>>;
  show: (route: string | null) => Promise<void>;
  rerender: () => Promise<void>;
};

/** A launch: no module state (every in-memory store empty); the device's files and keychain kept. */
async function launch(): Promise<App> {
  const clock = Date.now();
  jest.resetModules();
  mockAppStateListeners.clear();
  const { AppState } = await import("react-native");
  AppState.currentState = "active";
  AppState.addEventListener = ((_type: string, listener: (state: string) => void) => {
    mockAppStateListeners.add(listener);
    return { remove: () => mockAppStateListeners.delete(listener) };
  }) as typeof AppState.addEventListener;
  process.env.RNTL_SKIP_AUTO_CLEANUP = "true";
  rtl = await import("@testing-library/react-native");
  jest.setSystemTime(clock);
  const [{ AuthProvider }, { ModelsProvider }, { TodosProvider }, { NetworkProvider, useNetwork }, { PushNotificationBootstrap }] =
    await Promise.all([
      import("@/contexts/AuthContext"),
      import("@/contexts/ModelsContext"),
      import("@/features/todos/context/TodosContext"),
      import("@/contexts/NetworkContext"),
      import("@/features/todos/components/PushNotificationBootstrap"),
    ]);
  const { useEffect } = await import("react");
  const { MockFocus } = (await import("expo-router")) as unknown as {
    MockFocus: (props: { value: boolean; children: ReactNode }) => ReactNode;
  };
  const StatusClock = () => {
    const { status } = useNetwork();
    useEffect(() => { statusChanges.push({ status, at: Date.now() }); }, [status]);
    return null;
  };
  const ChatScreen = (await import("@/features/chat/screens/ChatScreen")).default;
  const routes: Record<string, () => ReactNode> = {
    memory: (await import("@/features/memory/screens/MemoryScreen")).default,
    memoryPage: (await import("@/features/memory/screens/MemoryDocumentScreen")).default,
    todos: (await import("@/features/todos/screens/TodosScreen")).default,
    gallery: (await import("@/features/attachments/screens/GalleryScreen")).default,
    settings: (await import("@/features/account/screens/SettingsScreen")).default,
    usage: (await import("@/features/account/screens/UsageScreen")).default,
    models: (await import("@/features/account/screens/ModelsSettingsScreen")).default,
    about: (await import("@/features/account/screens/AboutScreen")).default,
    archived: (await import("@/features/account/screens/ArchivedChatsScreen")).default,
    dataControls: (await import("@/features/account/screens/DataControlsScreen")).default,
    help: (await import("@/features/account/screens/HelpScreen")).default,
    memorySettings: (await import("@/features/memory/screens/MemorySettingsScreen")).default,
    notifications: (await import("@/features/account/screens/NotificationsSettingsScreen")).default,
    preferences: (await import("@/features/account/screens/PreferencesSettingsScreen")).default,
    profile: (await import("@/features/account/screens/ProfileSettingsScreen")).default,
    security: (await import("@/features/account/screens/SecuritySettingsScreen")).default,
    voice: (await import("@/features/account/screens/VoiceSettingsScreen")).default,
  };
  let top: string | null = null;
  // The chat screen is the stack's root: it stays mounted under every screen pushed on it.
  const tree = () => {
    const Top = top ? routes[top] : null;
    return (
      <AuthProvider>
        <ModelsProvider>
          <TodosProvider>
            <NetworkProvider>
              <StatusClock />
              <PushNotificationBootstrap />
              <MockFocus value={!Top}>
                <ChatScreen />
              </MockFocus>
              {Top ? <Top /> : null}
            </NetworkProvider>
          </TodosProvider>
        </ModelsProvider>
      </AuthProvider>
    );
  };
  const ui = await rtl.render(tree());
  const rerender = async () => { await ui.rerender(tree()); };
  mockRerender = rerender;
  return {
    ui,
    rerender,
    show: async (route) => {
      top = route;
      await rerender();
    },
  };
}

async function openChat(app: App, n: number, ms = 3000): Promise<void> {
  mockParams = { chatId: chatId(n) };
  await app.rerender();
  await settle(ms);
}

async function send(app: App, text: string): Promise<void> {
  await rtl.fireEvent.changeText(app.ui.getByTestId("chat-composer-input"), text);
  await settle(200);
  await rtl.fireEvent.press(app.ui.getByLabelText("chat.send_a11y"));
}

const SCREENS = [
  "memory", "todos", "gallery", "settings", "usage", "models", "about", "archived", "dataControls", "help",
  "memorySettings", "notifications", "preferences", "profile", "security", "voice",
];
/** A screen's read on opening it (none: it shows what the app already holds). */
const SCREEN_READS: Record<string, number> = {
  memory: 1, gallery: 1, usage: 1, archived: 1, memorySettings: 1, security: 1,
};

/** Screens opened a second time, whose read the server answers 304. */
const REVISITED = ["memory", "security"];

/** The most requests and sockets each step may send. */
const CEILINGS: Record<string, number> = {
  // /auth/me, the day's usage (free plan), to-dos, models, the check, the push token, the drawer.
  "cold start after sign-in": 7,
  // The newest page, each file's status (three), the socket.
  "open chat 1": 5,
  "open chat 2": 2,
  // The page this run kept is shown without a read; the socket reopens.
  "open chat 1 again within 20 s": 1,
  "send in chat 1": 0,
  "the reply finishes": 0,
  "20 s after the reply": 0,
  // The reply changed the to-do list: one read of it.
  "a reply that changes a to-do": 1,
  "open the drawer": 0,
  ...Object.fromEntries(SCREENS.map((name) => [`open ${name}`, SCREEN_READS[name] ?? 0])),
  ...Object.fromEntries(SCREENS.map((name) => [`leave ${name}`, 0])),
  // Memory and Security read on every visit; unchanged, the second read is a 304 (asserted below).
  ...Object.fromEntries(REVISITED.map((name) => [`open ${name} again`, 1])),
  ...Object.fromEntries(REVISITED.map((name) => [`leave ${name} again`, 0])),
  "a minute in the background": 0,
  // To-dos and the open chat (ETag, 304), the check, the socket.
  "return after a minute": 4,
  // And the model list (older than 5 minutes).
  "return after 10 minutes": 5,
  // iOS goes inactive and back without leaving: nothing is read again.
  "Control Centre and back, 6 minutes on": 0,
  // The zone sent to the server, and the to-dos read again for their new notify_at.
  "the phone's zone changes while the app runs": 2,
  // A return's reads, the zone sent, and the to-dos read once: after the zone landed.
  "return after 10 minutes, in another zone": 6,
  "50 minutes in the foreground": 0,
  // One refresh before the read, then the page and the socket.
  "open chat 2 after the token expired": 3,
  // One read per chat passed through, then the last one's socket.
  "switch chats 3 to 6 quickly": 5,
  "new chat": 0,
  // The chat, its socket, and the title read until the topic job has written it.
  "send in a new chat": 2 + TITLE_AFTER_READS + 1,
  "20 s after the new chat's reply": 0,
  // No push registration this time: the last one is under 12 hours old.
  "cold start again": 6,
  // The page; the files' statuses the first run settled come from disk.
  "open chat 1 after the relaunch": 2,
  // The token has expired: one refresh, which answers with the account (no /auth/me),
  // then the day's usage, to-dos, models, the check and the drawer.
  "cold start two hours later": 6,
};

jest.setTimeout(120_000);

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date(NOW));
  setTestTimeZone(HOME_ZONE);
  profileZone = HOME_ZONE;
  installServer();
});

it("keeps every step of an everyday session within its requests", async () => {
  mockSecure.set("recall_session_v1", JSON.stringify({ accessToken: accessToken(NOW_S + 3600), refreshToken: "r" }));
  mockFiles.set("file:///cache/cached-user.json", JSON.stringify({
    id: USER_ID, name: "Ann", avatar_url: null, plan: "free", ai_data_consent_at: NOW, locale: "en",
  }));
  let app = await launch();
  await settle(10_000);
  step("cold start after sign-in");

  await openChat(app, 1);
  step("open chat 1");
  await openChat(app, 2);
  step("open chat 2");
  await openChat(app, 1);
  step("open chat 1 again within 20 s");

  await send(app, "Hello there");
  await settle(400);
  step("send in chat 1");
  await settle(1500);
  step("the reply finishes");
  await settle(20_000);
  step("20 s after the reply");
  nextReplyChangesTodos = true;
  await send(app, "Remind me to call Sam at 5");
  await settle(3000);
  step("a reply that changes a to-do");

  const { openDrawer, closeDrawer } = await import("@/features/chat/drawer/drawer");
  await rtl.act(async () => { openDrawer(); });
  await settle(2000);
  await rtl.act(async () => { closeDrawer(); });
  await settle(500);
  step("open the drawer");

  for (const name of SCREENS) {
    await app.show(name);
    await settle(3000);
    step(`open ${name}`);
    await app.show(null);
    await settle(500);
    step(`leave ${name}`);
  }
  for (const name of REVISITED) {
    await app.show(name);
    await settle(3000);
    step(`open ${name} again`);
    await app.show(null);
    await settle(500);
    step(`leave ${name} again`);
  }

  await appState("background");
  await settle(60_000);
  step("a minute in the background");
  await appState("active");
  await settle(3000);
  step("return after a minute");
  await appState("background");
  await settle(10 * 60_000);
  await appState("active");
  await settle(3000);
  step("return after 10 minutes");
  await settle(6 * 60_000);
  await appState("inactive");
  await settle(1000);
  await appState("active");
  await settle(3000);
  step("Control Centre and back, 6 minutes on");

  setTestTimeZone(deviceZone() === "America/St_Johns" ? "Asia/Kathmandu" : "America/St_Johns");
  await rtl.act(async () => { for (const listener of [...mockClockListeners]) listener(); });
  await settle(3000);
  step("the phone's zone changes while the app runs");
  await appState("background");
  await settle(10 * 60_000);
  setTestTimeZone(deviceZone() === "Pacific/Kiritimati" ? "Asia/Kathmandu" : "Pacific/Kiritimati");
  await appState("active");
  await settle(3000);
  step("return after 10 minutes, in another zone");

  await settle(50 * 60_000);
  step("50 minutes in the foreground");
  await openChat(app, 2);
  step("open chat 2 after the token expired");

  for (const n of [3, 4, 5, 6]) {
    mockParams = { chatId: chatId(n) };
    await app.rerender();
    await settle(50);
  }
  await settle(3000);
  step("switch chats 3 to 6 quickly");

  mockParams = {};
  await app.rerender();
  await settle(1000);
  step("new chat");
  await send(app, "A new question");
  await settle(10_000);
  step("send in a new chat");
  await settle(20_000);
  step("20 s after the new chat's reply");

  app.ui.unmount();
  await settle(100);
  mark = mockLog.length;
  mockParams = {};
  app = await launch();
  await settle(10_000);
  step("cold start again");
  await openChat(app, 1);
  step("open chat 1 after the relaunch");

  app.ui.unmount();
  await settle(100);
  jest.setSystemTime(Date.now() + 2 * 60 * 60_000);
  mark = mockLog.length;
  mockParams = {};
  app = await launch();
  await settle(10_000);
  step("cold start two hours later");

  expectWithin(CEILINGS);
  // A zone is sent once when it changes, and a return that finds the server's zone sends none.
  const zoneReads = (title: string) => {
    const requests = steps.find((s) => s.title === title)?.requests ?? [];
    return [requests.filter((r) => r === "PATCH /auth/me").length, requests.filter((r) => r.startsWith("GET /todos/page")).length];
  };
  expect(["return after a minute", "return after 10 minutes", "the phone's zone changes while the app runs",
    "return after 10 minutes, in another zone"].map(zoneReads)).toEqual([[0, 1], [0, 1], [1, 1], [1, 1]]);
  expect(steps.filter((s) => s.requests.includes("PATCH /auth/me")).map((s) => s.title)).toEqual([
    "the phone's zone changes while the app runs", "return after 10 minutes, in another zone",
  ]);
  expect(steps.find((s) => s.title === "open memory again")?.requests).toEqual(["GET /memories/documents (304)"]);
  expect(steps.find((s) => s.title === "open security again")?.requests).toEqual(["GET /auth/sessions (304)"]);
});

/** Every step this test took stayed under its ceiling, and every ceiling was a step. */
function expectWithin(ceilings: Record<string, number>): void {
  if (process.env.CENSUS) {
    console.log(steps.map((s) => `${s.title} (${s.requests.length})\n${s.requests.map((r) => `  ${r}`).join("\n")}`)
      .join("\n"));
  }
  const over = steps
    .filter((s) => s.requests.length > (ceilings[s.title] ?? 0))
    .map((s) => `${s.title}: ${s.requests.length} > ${ceilings[s.title] ?? 0}\n  ${s.requests.join("\n  ")}`);
  expect(over).toEqual([]);
  expect(steps.map((s) => s.title).sort()).toEqual(Object.keys(ceilings).sort());
}

/**
 * The most each step may send while the API is out. Nothing retries in a loop but the
 * connection check while the banner shows, backing off: what failed is read again on the
 * user's next move or once the API is back, and the phones an outage refused together do
 * not come back in step.
 */
const OUTAGE_CEILINGS: Record<string, number> = {
  "cold start after sign-in": 7,
  "open chat 1": 5,
  // The sockets close (1012) and nothing reconnects until the user moves.
  "a deploy with the chat open, down 30 s, then a minute": 0,
  // One socket try; the next waits out its backoff. Refused, it asks for a connection check
  // (the API, then Google), which shows the banner; its loop checks again 1.5 s later, and may
  // a third time within the 5 s (3 s on, a fifth early). Before, a socket asked for none.
  "typing while the API is down": 7,
  // The deploy closed the socket: the send opens one. Before it, the loop's check finds the API
  // back and the page on screen is read again (a 304): the banner the socket's refusal showed.
  "send in chat 1": 3,
  // The reply's socket closes mid-stream. The phone reads the chat's newest rows until the
  // reply is saved, waiting as long as each 503's Retry-After (5 s) asks: at 1.5 to 2.5 s, then 5
  // to 6.25 s apart, so five or six (at 2 s apart it was fourteen). The first 503 asks for a
  // connection check (the API, then Google), which shows the banner; its loop checks again at
  // 1.5 s, 3 s, 6 s and 12 s (five checks, ten requests; before, no check and no banner).
  "a deploy mid-reply, 503 Retry-After 5 for 30 s": 16,
  // Back: the next read finds the saved reply, then the full page. The first of them clears the
  // banner (the loop's check, 20 s later, did) and asks for no second read of the page (a 304
  // before): one landed since the outage.
  "the 30 s after, the API back": 2,
  "a minute in the background": 0,
  // The return's reads (to-dos, the chat, the socket) fail once; the connection check backs off
  // (1.5 s, 3 s, 6 s, 12 s, 24 s), each asking Google whether it is the API. Once it passes, the
  // page on screen is read again, 0 to 10 s later.
  "return while the API is down 30 s, then 30 s": 15,
  // One socket try, then the send over SSE, refused: the phone says so and stops. The 503 asks
  // for a connection check, which shows the banner; its loop checks again at 1.5 s and 3 s.
  "send while the API answers 503": 8,
  // The loop's check finds the API back and clears the banner; the page on screen is read again.
  "a minute after the outage": 2,
};

it("keeps a server outage within its requests, with nothing in a loop", async () => {
  // Every spread (the check loop's jitter, the 0-10 s reconnect read) at its middle: with them
  // random, a reconnect read now and then slipped past its step into the next one's ceiling.
  const random = jest.spyOn(Math, "random").mockReturnValue(0.5);
  steps.length = 0;
  mockSecure.clear();
  mockFiles.clear();
  mockSecure.set("recall_session_v1", JSON.stringify({ accessToken: accessToken(NOW_S + 3600), refreshToken: "r" }));
  mockFiles.set("file:///cache/cached-user.json", JSON.stringify({
    id: USER_ID, name: "Ann", avatar_url: null, plan: "free", ai_data_consent_at: NOW, locale: "en",
  }));
  mark = mockLog.length;
  mockParams = {};
  const app = await launch();
  await settle(10_000);
  step("cold start after sign-in");
  await openChat(app, 1);
  step("open chat 1");

  await rtl.act(async () => { restartServer(); });
  outage = "down";
  await settle(30_000);
  outage = null;
  await settle(60_000);
  step("a deploy with the chat open, down 30 s, then a minute");

  outage = "down";
  await rtl.fireEvent.changeText(app.ui.getByTestId("chat-composer-input"), "Hel");
  await settle(5_000);
  outage = null;
  step("typing while the API is down");
  await settle(30_000);

  await send(app, "Hello there");
  await settle(300);
  step("send in chat 1");
  await rtl.act(async () => { restartServer(); });
  outage = { status: 503, retryAfter: "5" };
  await settle(30_000);
  step("a deploy mid-reply, 503 Retry-After 5 for 30 s");
  outage = null;
  savedTurn = [
    { id: uuid(2, 900), role: "user", content: "Hello there", model: null, created_at: NOW },
    { id: uuid(2, 901), role: "assistant", content: "Hi.", model: null, created_at: NOW },
  ];
  await settle(30_000);
  step("the 30 s after, the API back");

  await appState("background");
  await settle(60_000);
  step("a minute in the background");
  outage = "down";
  await appState("active");
  await settle(30_000);
  outage = null;
  await settle(30_000);
  step("return while the API is down 30 s, then 30 s");

  outage = { status: 503, retryAfter: "5" };
  await send(app, "Are you there");
  await settle(10_000);
  outage = null;
  step("send while the API answers 503");
  await settle(60_000);
  step("a minute after the outage");
  random.mockRestore();

  expectWithin(OUTAGE_CEILINGS);
});

const CHAT_1_PAGE = `GET /chats/${chatId(1)}/messages?limit=40`;

/**
 * Where the user is when the API comes back, and the read of the list on screen then (null:
 * no list is on screen). Each case is undone by the next one's `show`, which then waits out the
 * stale window: a list read moments before the outage is not read again.
 */
type RecoveryCase = { title: string; show: (app: App) => Promise<void>; read: RegExp | null };

async function showOnly(app: App, route: string | null, params: Record<string, string> = {}): Promise<void> {
  const { closeDrawer } = await import("@/features/chat/drawer/drawer");
  await rtl.act(async () => { closeDrawer(); });
  mockParams = { chatId: chatId(1), ...params };
  await app.show(route);
  await settle(20_000);
}

const RECOVERY_CASES: RecoveryCase[] = [
  { title: "the open chat", show: (app) => showOnly(app, null), read: /^GET \/chats\/[^/]+\/messages\?limit=40\b/ },
  {
    title: "the drawer open over the chat",
    show: async (app) => {
      await showOnly(app, null);
      const { openDrawer } = await import("@/features/chat/drawer/drawer");
      await rtl.act(async () => { openDrawer(); });
      await settle(20_000);
    },
    read: /^GET \/chats\?client_timezone=[^&\s]+(?: \(304\))?$/,
  },
  { title: "the to-do list", show: (app) => showOnly(app, "todos"), read: /^GET \/todos\/page\b/ },
  { title: "the memory list", show: (app) => showOnly(app, "memory"), read: /^GET \/memories\/documents(?: \(304\))?$/ },
  {
    title: "a memory page",
    show: (app) => showOnly(app, "memoryPage", { key: "profile" }),
    read: /^GET \/memories\/documents(?: \(304\))?$/,
  },
  { title: "the library", show: (app) => showOnly(app, "gallery"), read: /^GET \/attachments\b/ },
  // Settings' two lists (useFocusedList): the archived chats come with the drawer's list.
  {
    title: "the archived chats",
    show: (app) => showOnly(app, "archived"),
    read: /^GET \/chats\?client_timezone=[^&\s]+(?: \(304\))?$/,
  },
  {
    title: "the signed-in devices",
    show: (app) => showOnly(app, "security"),
    read: /^GET \/auth\/sessions(?: \(304\))?$/,
  },
  // Settings' two pages that read on opening, not lists: the day's usage and memory's count.
  { title: "the day's usage", show: (app) => showOnly(app, "usage"), read: /^GET \/chats\/usage\/today$/ },
  { title: "memory settings", show: (app) => showOnly(app, "memorySettings"), read: /^GET \/memories$/ },
  { title: "settings, no list", show: (app) => showOnly(app, "settings"), read: null },
  {
    title: "a new chat, no list",
    show: async (app) => {
      await showOnly(app, null);
      mockParams = {};
      await app.rerender();
      await settle(20_000);
    },
    read: null,
  },
];

/** The API refuses a return from the background: the return's reads fail and the banner shows. */
async function returnIntoOutage(): Promise<void> {
  await appState("background");
  await settle(1000);
  outage = "down";
  await appState("active");
  await settle(5000);
}

/** Until the connection check passes and the banner clears; the read after it is still waiting. */
async function untilBannerClears(): Promise<void> {
  for (let waited = 0; statusChanges[statusChanges.length - 1]?.status !== "online"; waited += 50) {
    if (waited > 60_000) throw new Error("the banner never cleared");
    await settle(50);
  }
}

/** Each list's read in a step: the to-dos, the open chat, the drawer, memory and the library. */
function listReads(requests: string[]): string[] {
  return requests.filter((r) => /^GET \/(todos\/page|chats\/[^/]+\/messages|chats\b(?!\/)|memories|attachments\?)/.test(r));
}

it("reads the list on screen again once, 0 to 10 s after an outage ends, and nothing else", async () => {
  steps.length = 0;
  mockSecure.clear();
  mockFiles.clear();
  mockSecure.set("recall_session_v1", JSON.stringify({ accessToken: accessToken(NOW_S + 3600), refreshToken: "r" }));
  mockFiles.set("file:///cache/cached-user.json", JSON.stringify({
    id: USER_ID, name: "Ann", avatar_url: null, plan: "free", ai_data_consent_at: NOW, locale: "en",
  }));
  mockParams = {};
  const app = await launch();
  await settle(10_000);
  await openChat(app, 1);
  mark = mockLog.length;

  const reads: { title: string; requests: string[] }[] = [];
  const wanted: typeof reads = [];
  /** How long after the banner cleared each list was read again. */
  const landed: Record<string, number> = {};
  for (const { title, show, read } of RECOVERY_CASES) {
    await show(app);
    mark = mockLog.length;
    await returnIntoOutage();
    step(`${title}: a return while the API is down`);
    outage = null;
    await settle(25_000);
    step(`${title}: the API back`);
    const back = steps[steps.length - 1];
    // Past the connection check that clears the banner: the list on screen, once.
    reads.push({ title, requests: back.requests.filter((r) => r !== `GET ${CHECK}`) });
    wanted.push({ title, requests: read ? [expect.stringMatching(read)] : [] });
    const reread = read && back.sent.find((r) => read.test(`${r.method} ${r.path}`));
    if (reread) {
      const cleared = statusChanges.filter((c) => c.status === "online" && c.at <= reread.at);
      landed[title] = reread.at - cleared[cleared.length - 1].at;
    }
  }
  if (process.env.CENSUS) console.log(steps.map((s) => `${s.title}\n  ${s.requests.join("\n  ")}`).join("\n"), landed);
  expect(reads).toEqual(wanted);
  for (const after of Object.values(landed)) {
    expect(after).toBeGreaterThanOrEqual(0);
    expect(after).toBeLessThan(10_000);
  }

  // The screen left as the API came back: its read is called off, and the chat under it has none.
  await RECOVERY_CASES[2].show(app);
  await returnIntoOutage();
  outage = null;
  mark = mockLog.length;
  await untilBannerClears();
  await app.show(null);
  await settle(15_000);
  step("the to-do list left as the API came back");
  expect(listReads(steps[steps.length - 1].requests)).toEqual([]);

  // The connection lost again during the wait (a move to another network finds the API down):
  // nothing is read; once the API is back, the list on screen is read once.
  await RECOVERY_CASES[2].show(app);
  await returnIntoOutage();
  outage = null;
  mark = mockLog.length;
  await untilBannerClears();
  outage = "down";
  await rtl.act(async () => {
    for (const listener of [...mockNetListeners]) listener({ ...mockNetState, type: "cellular", details: null });
  });
  await settle(15_000);
  step("the to-do list, the API gone again during the wait");
  expect(listReads(steps[steps.length - 1].requests)).toEqual([]);
  expect(statusChanges[statusChanges.length - 1].status).toBe("api_unreachable");
  outage = null;
  await settle(40_000);
  step("the to-do list, the API back again");
  expect(listReads(steps[steps.length - 1].requests)).toEqual([expect.stringMatching(/^GET \/todos\/page\b/)]);

  // The outage ends while the app is in the background: nothing is read then, and the return
  // reads what any return does (to-dos, the models, the open chat, the check, the socket): the
  // chat once, the read the API's return asks for falling within its stale window.
  await RECOVERY_CASES[0].show(app);
  await returnIntoOutage();
  mark = mockLog.length;
  await appState("background");
  outage = null;
  await settle(60_000);
  step("the API back while the app is in the background");
  expect(steps[steps.length - 1].requests).toEqual([]);
  await appState("active");
  await settle(15_000);
  step("the return after it");
  const back = steps[steps.length - 1].requests;
  expect(back.filter((r) => r.startsWith(CHAT_1_PAGE))).toHaveLength(1);
  expect(back.length).toBeLessThanOrEqual(CEILINGS["return after 10 minutes"]);
});

it("reads a list on screen as the API came back once: its own read is the reconnect's", async () => {
  // Each spread at its middle: the loop checks 1.5, 4.5, 10.5 and 22.5 s into the outage, then at
  // 46.5 s. The API is back at 25 s, when the user opens the list: that read lands at once.
  const random = jest.spyOn(Math, "random").mockReturnValue(0.5);
  steps.length = 0;
  mockSecure.clear();
  mockFiles.clear();
  mockSecure.set("recall_session_v1", JSON.stringify({ accessToken: accessToken(NOW_S + 3600), refreshToken: "r" }));
  mockFiles.set("file:///cache/cached-user.json", JSON.stringify({
    id: USER_ID, name: "Ann", avatar_url: null, plan: "free", ai_data_consent_at: NOW, locale: "en",
  }));
  mockParams = {};
  const app = await launch();
  await settle(10_000);
  await openChat(app, 1);

  const reads: { title: string; reads: string[] }[] = [];
  for (const { title, show, read } of RECOVERY_CASES) {
    if (!read) continue;
    await showOnly(app, "settings");
    await returnIntoOutage();
    await settle(20_000);
    outage = null;
    mark = mockLog.length;
    await show(app);
    await settle(10_000);
    step(`${title}: opened as the API came back`);
    reads.push({ title, reads: steps[steps.length - 1].requests.filter((r) => read.test(r)) });
    expect(statusChanges[statusChanges.length - 1].status).toBe("online");
  }
  random.mockRestore();
  if (process.env.CENSUS) console.log(steps.map((s) => `${s.title}\n  ${s.requests.join("\n  ")}`).join("\n"));
  // Once: on opening it, or, for a list the screen shows as it holds it, once the API is back.
  // Before, a list read on opening was read again 0 to 10 s after the loop's check, 26.5 s later.
  expect(reads).toEqual(reads.map(({ title }) => ({ title, reads: [expect.any(String)] })));
});

it("clears the banner at the first 200 after an outage and reads the open chat once", async () => {
  // Each spread at its middle: the reply's page lands 30 s in. The loop's check that cleared the
  // banner ran at 50 s, and the read it asked for would come 5 s later, past the page's window.
  const random = jest.spyOn(Math, "random").mockReturnValue(0.5);
  steps.length = 0;
  savedTurn = [];
  mockSecure.clear();
  mockFiles.clear();
  mockSecure.set("recall_session_v1", JSON.stringify({ accessToken: accessToken(NOW_S + 3600), refreshToken: "r" }));
  mockFiles.set("file:///cache/cached-user.json", JSON.stringify({
    id: USER_ID, name: "Ann", avatar_url: null, plan: "free", ai_data_consent_at: NOW, locale: "en",
  }));
  mockParams = {};
  const app = await launch();
  await settle(10_000);
  await openChat(app, 1);
  await send(app, "Hello there");
  await settle(300);
  await rtl.act(async () => { restartServer(); });
  outage = { status: 503, retryAfter: "5" };
  await settle(30_000);
  outage = null;
  savedTurn = [
    { id: uuid(2, 900), role: "user", content: "Hello there", model: null, created_at: NOW },
    { id: uuid(2, 901), role: "assistant", content: "Hi.", model: null, created_at: NOW },
  ];
  expect(statusChanges[statusChanges.length - 1].status).toBe("api_unreachable");
  mark = mockLog.length;
  const since = statusChanges.length;
  await settle(30_000);
  step("the reply's page, then the API's return seen");
  random.mockRestore();
  const { requests: back, sent } = steps[steps.length - 1];
  if (process.env.CENSUS) console.log(back);
  // The reply's newest rows, then its page. The first 200 clears the banner, at once: no check.
  const first = sent.find((r) => r.status === 200);
  const cleared = statusChanges.slice(since).filter((c) => c.status === "online");
  expect(cleared).toHaveLength(1);
  expect(cleared[0].at - first!.at).toBeGreaterThanOrEqual(0);
  expect(cleared[0].at - first!.at).toBeLessThan(50);
  expect(back.filter((r) => r.startsWith(`GET ${CHECK}`))).toEqual([]);
  expect(statusChanges[statusChanges.length - 1].status).toBe("online");
  expect(listReads(back)).toEqual([`GET /chats/${chatId(1)}/messages?limit=4`, CHAT_1_PAGE]);
});

/**
 * Reads that find no API with the app open, and no network change or return to tell the
 * connection check: the reads of a quick switch through four chats, refused or answered 503.
 * With the database or Redis down, /health still answers 200: the check read it and found the
 * API "online", so no banner showed and nothing was read again when the outage ended.
 */
const UNSEEN_OUTAGES: { title: string; outage: Outage }[] = [
  { title: "refused", outage: "down" },
  { title: "503", outage: { status: 503, retryAfter: "5" } },
  { title: "a dependency down", outage: { status: 503, retryAfter: "5", live: true } },
  // Redis down: the API's request limiter cannot count, so every read answers its own 503
  // "unavailable". It answered 429 "Rate limit unavailable", which the phone reads as a limit:
  // no check, no banner, and nothing read again once Redis was back. Liveness still answers.
  { title: "Redis down", outage: { status: 503, retryAfter: "5", live: true, code: "unavailable" } },
];

it("checks the connection once for a burst of reads that find no API, then reads the page again", async () => {
  steps.length = 0;
  mockSecure.clear();
  mockFiles.clear();
  mockSecure.set("recall_session_v1", JSON.stringify({ accessToken: accessToken(NOW_S + 3600), refreshToken: "r" }));
  mockFiles.set("file:///cache/cached-user.json", JSON.stringify({
    id: USER_ID, name: "Ann", avatar_url: null, plan: "free", ai_data_consent_at: NOW, locale: "en",
  }));
  mockParams = {};
  const app = await launch();
  await settle(10_000);
  await openChat(app, 1);

  for (const { title, outage: kind } of UNSEEN_OUTAGES) {
    await showOnly(app, null);
    mark = mockLog.length;
    const since = statusChanges.length;
    outage = kind;
    for (const n of [3, 4, 5, 6]) {
      mockParams = { chatId: chatId(n) };
      await app.rerender();
      await settle(50);
    }
    await settle(10_000);
    step(`${title}: four chats opened while the API is out`);
    const out = steps[steps.length - 1];
    const banner = statusChanges.slice(since).find((c) => c.status !== "online");
    // The banner shows. Before it did, the failed requests (four reads, three empty-chat deletes)
    // had sent one connection check: the API, then Google.
    expect(banner?.status).toBe("api_unreachable");
    const failed = out.sent.filter((r) => r.path !== CHECK && !r.path.startsWith("google/") && r.status !== 200);
    expect(failed.length).toBeGreaterThanOrEqual(4);
    const checks = out.sent.filter((r) => r.path === CHECK && r.at <= (banner?.at ?? -1));
    expect(checks).toHaveLength(1);
    // The loop's first wait (1.5 s, a fifth either way) after the first failure.
    expect(checks[0].at - failed[0].at).toBeGreaterThanOrEqual(1_200);
    expect(checks[0].at - failed[0].at).toBeLessThanOrEqual(1_850);

    outage = null;
    mark = mockLog.length;
    await untilBannerClears();
    await settle(15_000);
    step(`${title}: the API back`);
    // The open chat's page, once, 0 to 10 s after the banner cleared.
    expect(listReads(steps[steps.length - 1].requests)).toEqual([
      expect.stringMatching(new RegExp(`^GET /chats/${chatId(6)}/messages\\?limit=40\\b`)),
    ]);
  }
  if (process.env.CENSUS) console.log(steps.map((s) => `${s.title}\n  ${s.requests.join("\n  ")}`).join("\n"));
});

const REDIS_DOWN: Outage = { status: 503, retryAfter: "5", live: true, code: "unavailable" };

/**
 * An outage only the chat's socket meets: no read fails to tell the connection check. A socket
 * reported none, so no banner showed and nothing was read again when the outage ended.
 */
const SOCKET_OUTAGES: { title: string; outage: Outage; before?: () => void; meet: (app: App) => Promise<void> }[] = [
  // The open socket answers a send `unavailable`, then closes 1013 (ws_api._close_while_down).
  { title: "Redis down, a send on the open socket", outage: REDIS_DOWN, meet: (app) => send(app, "Hello there") },
  // A deploy closed the socket (1012, no check); typing opens one, which the outage meets.
  {
    title: "Redis down, a new socket", outage: REDIS_DOWN, before: restartServer,
    meet: (app) => rtl.fireEvent.changeText(app.ui.getByTestId("chat-composer-input"), "Hel"),
  },
  {
    title: "a new socket refused", outage: "down", before: restartServer,
    meet: (app) => rtl.fireEvent.changeText(app.ui.getByTestId("chat-composer-input"), "Hel"),
  },
  // The open socket drops (no close frame) with the API gone.
  { title: "the open socket dropped", outage: "down", meet: () => rtl.act(async () => { dropSockets(1006); }) },
];

it("checks the connection once for a socket that meets an outage, and shows the banner", async () => {
  steps.length = 0;
  socketDrops.length = 0;
  mockSecure.clear();
  mockFiles.clear();
  mockSecure.set("recall_session_v1", JSON.stringify({ accessToken: accessToken(NOW_S + 3600), refreshToken: "r" }));
  mockFiles.set("file:///cache/cached-user.json", JSON.stringify({
    id: USER_ID, name: "Ann", avatar_url: null, plan: "free", ai_data_consent_at: NOW, locale: "en",
  }));
  mockParams = {};
  const app = await launch();
  await settle(10_000);

  for (const [i, { title, outage: kind, before, meet }] of SOCKET_OUTAGES.entries()) {
    // A chat not opened before: its socket opens with no failure behind it.
    await openChat(app, 10 + i, 20_000);
    if (before) await rtl.act(async () => { before(); });
    await settle(1000);
    mark = mockLog.length;
    const since = statusChanges.length;
    outage = kind;
    const metAt = Date.now();
    await meet(app);
    await settle(10_000);
    step(`${title}: the socket meets the outage`);
    const out = steps[steps.length - 1];
    const banner = statusChanges.slice(since).find((c) => c.status !== "online");
    expect({ title, banner: banner?.status }).toEqual({ title, banner: "api_unreachable" });
    // Before the banner: the new socket, if one opened, then one check (the API, then Google).
    const shown = out.sent.filter((r) => r.at <= (banner?.at ?? -1));
    expect(shown.map((r) => (r.method === "WS" ? "WS" : r.path)))
      .toEqual([...(before ? ["WS"] : []), CHECK, "google/generate_204"]);
    // The loop's first wait (1.5 s, a fifth either way) after the server closed the socket.
    const dropped = socketDrops.filter((at) => at >= metAt);
    expect(dropped).toHaveLength(1);
    expect(shown[shown.length - 2].at - dropped[0]).toBeGreaterThanOrEqual(1_200);
    expect(shown[shown.length - 2].at - dropped[0]).toBeLessThanOrEqual(1_850);

    outage = null;
    await untilBannerClears();
    await settle(15_000);
  }
  if (process.env.CENSUS) console.log(steps.map((s) => `${s.title}\n  ${s.requests.join("\n  ")}`).join("\n"));
});
