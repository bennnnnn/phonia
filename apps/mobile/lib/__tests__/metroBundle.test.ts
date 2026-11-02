/**
 * What metro.config.js adds to the bundle and what it leaves out. The
 * RevenueCat rule leans on how react-native-purchases loads its web SDK, so the
 * real package is loaded here the way a native production bundle has it.
 */
declare const __dirname: string;

type Resolution = { type: string; filePath?: string };
type ResolveRequest = (
  context: Record<string, unknown>,
  moduleName: string,
  platform: string | null,
) => Resolution;
type MetroConfig = { resolver: { assetExts: string[]; resolveRequest: ResolveRequest } };

const { join } = jest.requireActual<{ join(...parts: string[]): string }>("node:path");
const fs = jest.requireActual<{
  existsSync(path: string): boolean;
  readdirSync(path: string, options: { withFileTypes: true }): { name: string; isDirectory(): boolean }[];
  readFileSync(path: string, encoding: "utf8"): string;
}>("node:fs");
// eslint-disable-next-line @typescript-eslint/no-require-imports -- the CommonJS config Metro loads
const config = require(join(__dirname, "..", "..", "metro.config.js")) as MetroConfig;

/** Resolves as Metro would for one bundle; the app's own resolver hands anything else on. */
function resolve(
  moduleName: string,
  { platform = "ios", dev = false, from = "/app/features/billing/model/purchases.ts" } = {},
): Resolution {
  const context = {
    dev,
    originModulePath: from,
    resolveRequest: (_context: unknown, name: string) => ({ type: "sourceFile", filePath: name }),
  };
  return config.resolver.resolveRequest(context, moduleName, platform);
}

const EMPTY = { type: "empty" };

describe("metro.config.js", () => {
  it("ships the preview WebViews' libraries (lib/vendor/*.txt) as assets", () => {
    expect(config.resolver.assetExts).toContain("txt");
  });

  it.each(["@sentry/replay", "@sentry/replay-canvas", "@sentry/feedback"])(
    "leaves Sentry's unused %s out of every bundle",
    (name) => {
      expect(resolve(name, { platform: "ios" })).toEqual(EMPTY);
      expect(resolve(name, { platform: "android", dev: true })).toEqual(EMPTY);
    },
  );

  it("leaves out the @sentry/browser modules that build the feedback widget on load", () => {
    const from = "/app/node_modules/@sentry/browser/build/npm/esm/prod/index.js";
    expect(resolve("./feedbackSync.js", { from })).toEqual(EMPTY);
    expect(resolve("./feedbackAsync.js", { from })).toEqual(EMPTY);
  });

  it("leaves RevenueCat's web SDK out of native production bundles only", () => {
    const sdk = "@revenuecat/purchases-js-hybrid-mappings";
    expect(resolve(sdk, { platform: "ios" })).toEqual(EMPTY);
    expect(resolve(sdk, { platform: "android" })).toEqual(EMPTY);
    // Development bundles (Expo Go, dev builds) and the web keep it.
    expect(resolve(sdk, { platform: "ios", dev: true })).toEqual({ type: "sourceFile", filePath: sdk });
    expect(resolve(sdk, { platform: "web" })).toEqual({ type: "sourceFile", filePath: sdk });
  });

  it.each([
    "@sentry/core",
    "@sentry/react-native",
    "@sentry/browser",
    "react-native-purchases",
    "@revenuecat/purchases-typescript-internal",
  ])(
    "resolves %s as before",
    (name) => {
      expect(resolve(name)).toEqual({ type: "sourceFile", filePath: name });
    },
  );
});

const APP = join(__dirname, "..", "..");
const ATTRIBUTES = "@sentry/conventions/attributes";
const ATTRIBUTE_IMPORT = /import\s*\{([^}]*)\}\s*from\s*["']@sentry\/conventions\/attributes["']/g;
const ATTRIBUTE_REQUIRE = /(?:const|var|let)\s+(\w+)\s*=\s*require\(["']@sentry\/conventions\/attributes["']\)/g;

/** Every .js/.mjs/.cjs file under `dir`. */
function scripts(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === "node_modules" ? [] : scripts(path);
    return /\.(?:m|c)?js$/.test(entry.name) ? [path] : [];
  });
}

/** The installed Sentry packages: each `.pnpm/@sentry+<name>@<version>…` folder's own package. */
function sentryPackages(): { name: string; dir: string }[] {
  const store = join(APP, "node_modules", ".pnpm");
  return fs
    .readdirSync(store, { withFileTypes: true })
    .map((entry) => /^@sentry\+([^@]+)@/.exec(entry.name) && { folder: entry.name, name: /^@sentry\+([^@]+)@/.exec(entry.name)![1] })
    .filter((found): found is { folder: string; name: string } => found !== null)
    .map(({ folder, name }) => ({ name, dir: join(store, folder, "node_modules", "@sentry", name) }));
}

/** The attribute names every installed Sentry package reads, by ESM import or CJS property. */
function attributeNamesSentryReads(): Set<string> {
  const names = new Set<string>();
  for (const { name, dir } of sentryPackages()) {
    if (name === "conventions" || !fs.existsSync(dir)) continue;
    for (const file of scripts(dir)) {
      const text = fs.readFileSync(file, "utf8");
      if (!text.includes(ATTRIBUTES)) continue;
      for (const [, list] of text.matchAll(ATTRIBUTE_IMPORT)) {
        for (const item of list.split(",")) {
          const imported = item.trim().split(/\s+as\s+/)[0];
          if (imported) names.add(imported);
        }
      }
      for (const [, binding] of text.matchAll(ATTRIBUTE_REQUIRE)) {
        // The package's names are constants (URL_FULL); a file name ("attributes.js") is not one.
        for (const [, read] of text.matchAll(new RegExp(`\\b${binding}\\.([A-Z_][A-Z0-9_]*)\\b`, "g"))) names.add(read);
      }
    }
  }
  return names;
}

describe("Sentry's attribute names (lib/sentryAttributes.js)", () => {
  it("replace @sentry/conventions/attributes in every bundle", () => {
    const shim = { type: "sourceFile", filePath: join(APP, "lib", "sentryAttributes.js") };
    expect(resolve(ATTRIBUTES, { platform: "ios" })).toEqual(shim);
    expect(resolve(ATTRIBUTES, { platform: "android", dev: true })).toEqual(shim);
  });

  it("hold every name the installed Sentry SDK reads, with the package's value", () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- the CommonJS file Metro serves
    const kept = require(join(APP, "lib", "sentryAttributes.js")) as Record<string, string>;
    const installed = sentryPackages()
      .filter((pkg) => pkg.name === "conventions")
      // eslint-disable-next-line @typescript-eslint/no-require-imports -- the package's own CommonJS build
      .map((pkg) => require(join(pkg.dir, "dist", "attributes.cjs")) as Record<string, unknown>);
    const read = attributeNamesSentryReads();
    expect(installed.length).toBeGreaterThan(0);
    expect(read.size).toBeGreaterThan(0);
    const wrong = [...read]
      .sort()
      .flatMap((name) => installed.map((values) => [name, values[name]] as const))
      .filter(([name, value]) => typeof value !== "string" || kept[name] !== value)
      .map(([name, value]) => `${name}: ${JSON.stringify(value)},`);
    expect(wrong).toEqual([]);
    // A name Sentry no longer reads is removed, so the file stays the list it reads.
    expect(Object.keys(kept).filter((name) => !read.has(name))).toEqual([]);
  });
});

type CustomerInfo = { entitlements: { active: Record<string, { productIdentifier: string }> } };

const PLUS: CustomerInfo = { entitlements: { active: { plus: { productIdentifier: "plus_monthly:monthly" } } } };
const PRO: CustomerInfo = { entitlements: { active: { pro: { productIdentifier: "pro_monthly:monthly" } } } };
const PRO_PACKAGE = {
  identifier: "pro_monthly",
  presentedOfferingContext: { offeringIdentifier: "default", placementIdentifier: null, targetingContext: null },
  product: { identifier: "pro_monthly:monthly", priceString: "$9.99" },
};

/** What the native store answers each method with; any other method returns nothing. */
const NATIVE_ANSWERS: Record<string, unknown> = {
  isConfigured: true,
  logIn: { customerInfo: PLUS, created: false },
  getOfferings: { all: {}, current: { availablePackages: [PRO_PACKAGE], monthly: null } },
  getCustomerInfo: PLUS,
  purchasePackage: { productIdentifier: "pro_monthly", customerInfo: PRO },
  restorePurchases: PLUS,
  logOut: { entitlements: { active: {} } },
};

/** Every call into RNPurchases, the native module. */
const mockNativeCalls: { method: string; args: unknown[] }[] = [];
const mockNativePurchases = new Proxy(
  {},
  {
    get: (_module, method) =>
      typeof method !== "string" || method === "then"
        ? undefined
        : (...args: unknown[]) => {
            mockNativeCalls.push({ method, args });
            return method in NATIVE_ANSWERS ? Promise.resolve(NATIVE_ANSWERS[method]) : undefined;
          },
  },
);
/** The native module's events, by name. */
const mockNativeEvents = new Map<string, (event: unknown) => void>();
/** Every read of the web SDK, which a native production bundle leaves empty. */
const mockWebSdkReads: string[] = [];
const mockPlatform = { OS: "ios" };

const nativeCalls = (method: string) =>
  mockNativeCalls.filter((call) => call.method === method).map((call) => call.args);

describe("react-native-purchases in a native production bundle (no web SDK)", () => {
  beforeEach(() => {
    jest.resetModules();
    mockNativeCalls.length = 0;
    mockNativeEvents.clear();
    mockWebSdkReads.length = 0;
    mockPlatform.OS = "ios";
    (globalThis as { __DEV__?: boolean }).__DEV__ = false;
    process.env.EXPO_PUBLIC_REVENUECAT_IOS_API_KEY = "ios_key";
    process.env.EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY = "android_key";
    // The web SDK as a native production bundle has it: nothing may read from it.
    jest.doMock(
      "@revenuecat/purchases-js-hybrid-mappings",
      () =>
        new Proxy(
          {},
          {
            get: (_module, name) => {
              mockWebSdkReads.push(String(name));
              throw new Error(`The web SDK was used: ${String(name)}`);
            },
          },
        ),
    );
    jest.doMock("react-native", () => ({
      NativeModules: { RNPurchases: mockNativePurchases },
      NativeEventEmitter: class {
        addListener(name: string, listener: (event: unknown) => void) {
          mockNativeEvents.set(name, listener);
          return { remove: () => undefined };
        }
      },
      Platform: {
        get OS() {
          return mockPlatform.OS;
        },
        select: (options: Record<string, unknown>) => options[mockPlatform.OS] ?? options.default,
      },
    }));
    jest.doMock("@/lib/expoRuntime", () => ({ isExpoGo: () => false }));
  });

  it("loads and configures on the native store", () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- loaded after the mocks above
    const { default: Purchases } = require("react-native-purchases") as typeof import("react-native-purchases");
    Purchases.configure({ apiKey: "appl_key", appUserID: "user-1" });
    expect(nativeCalls("setupPurchases").map((args) => args.slice(0, 2))).toEqual([["appl_key", "user-1"]]);
    expect(mockWebSdkReads).toEqual([]);
  });

  it.each(["ios", "android"])("serves every call features/billing/model/purchases.ts makes from the native store on %s", async (os) => {
    mockPlatform.OS = os;
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- loaded after the mocks above
    const purchases = require("@/features/billing/model/purchases") as typeof import("@/features/billing/model/purchases");
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- the same module features/billing/model/purchases.ts loads
    const { default: Purchases } = require("react-native-purchases") as typeof import("react-native-purchases");

    await purchases.configurePurchases("user-1");
    await purchases.configurePurchases("user-2");
    const { pro } = (await purchases.getPlanPackages()).packages;
    expect(pro).toMatchObject({ plan: "pro", priceString: "$9.99", productId: "pro_monthly:monthly" });
    await expect(purchases.purchasePlanPackage(pro!)).resolves.toBe("pro");
    await expect(purchases.restorePurchases()).resolves.toBe("plus");

    const plans: string[] = [];
    const stop = await purchases.registerPlanChangeListener((plan) => plans.push(plan));
    mockNativeEvents.get("Purchases-CustomerInfoUpdated")?.(PRO);
    stop?.();
    mockNativeEvents.get("Purchases-CustomerInfoUpdated")?.(PLUS);
    expect(plans).toEqual(["pro"]);
    await purchases.signOutRevenueCat();

    expect(nativeCalls("setLogLevel")).toEqual([["WARN"]]);
    expect(nativeCalls("setupPurchases").map((args) => args.slice(0, 2))).toEqual([[`${os}_key`, "user-1"]]);
    expect(nativeCalls("logIn")).toEqual([["user-2"]]);
    expect(nativeCalls("getOfferings")).toEqual([[]]);
    // Android: Pro replaces the Plus subscription, prorated.
    expect(typeof Purchases.PRORATION_MODE.IMMEDIATE_WITH_TIME_PRORATION).toBe("number");
    const change =
      os === "android"
        ? { oldProductIdentifier: "plus_monthly", prorationMode: Purchases.PRORATION_MODE.IMMEDIATE_WITH_TIME_PRORATION }
        : null;
    expect(nativeCalls("getCustomerInfo")).toEqual(os === "android" ? [[]] : []);
    expect(nativeCalls("purchasePackage")).toEqual([
      ["pro_monthly", PRO_PACKAGE.presentedOfferingContext, change, null, null],
    ]);
    expect(nativeCalls("restorePurchases")).toEqual([[]]);
    expect(nativeCalls("logOut")).toEqual([[]]);
    expect(mockWebSdkReads).toEqual([]);
  });
});
