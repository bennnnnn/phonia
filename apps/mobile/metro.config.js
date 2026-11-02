const fs = require("fs");
const path = require("path");
const { getDefaultConfig } = require("expo/metro-config");
const { withSentryFeedbackResolver, withSentryResolver } = require("@sentry/react-native/metro");

/** @type {import('expo/metro-config').MetroConfig} */
const config = getDefaultConfig(__dirname);

/**
 * Pin react-native-svg to a single physical copy (pnpm can otherwise hand
 * Metro two and Android double-registers RNSVGCircle). Resolve via Metro so
 * the package.json "react-native" field (`src/`) is used — Node's
 * require.resolve picks lib/commonjs and skips Fabric codegen.
 */
const dedupedModules = new Set(["react-native-svg"]);
const appPackageJson = path.join(__dirname, "package.json");
const webrtcInstalled = fs.existsSync(path.join(__dirname, "node_modules/react-native-webrtc"));
const webrtcStub = path.join(__dirname, "lib/webrtcStub.js");
/**
 * RevenueCat's web SDK. react-native-purchases runs it only in its browser mode
 * (Expo Go, web), which a native production build never enters, and
 * features/billing/model/purchases.ts does not load purchases in Expo Go at all. Production iOS and
 * Android bundles leave it out; development bundles keep it, so Expo Go is
 * unchanged. lib/__tests__/metroBundle.test.ts loads react-native-purchases
 * without it, so an update that needs it sooner fails there.
 */
const REVENUECAT_WEB_SDK = "@revenuecat/purchases-js-hybrid-mappings";
/**
 * Sentry reads 29 of the 745 names in @sentry/conventions/attributes; the rest of the
 * module, with its registry of every attribute's type and description, is about 300 KB
 * the app never reads. Every bundle takes lib/sentryAttributes.js instead, which
 * lib/__tests__/metroBundle.test.ts checks against the installed package.
 */
const SENTRY_ATTRIBUTES = "@sentry/conventions/attributes";
const sentryAttributes = path.join(__dirname, "lib/sentryAttributes.js");

config.resolver.resolveRequest = (context, moduleName, platform) => {
  const root = moduleName.split("/")[0];
  if (dedupedModules.has(root)) {
    return context.resolveRequest(
      { ...context, originModulePath: appPackageJson },
      moduleName,
      platform,
    );
  }
  // Metro still extracts require("react-native-webrtc") from speech/realtimeVoice.ts
  // at bundle time. Without a fallback, a missing install red-screens the
  // whole chat screen — not just Live Talk.
  if (moduleName === "react-native-webrtc" && !webrtcInstalled) {
    return { type: "sourceFile", filePath: webrtcStub };
  }
  if (moduleName === REVENUECAT_WEB_SDK && !context.dev && platform !== "web") {
    return { type: "empty" };
  }
  if (moduleName === SENTRY_ATTRIBUTES) {
    return { type: "sourceFile", filePath: sentryAttributes };
  }
  return context.resolveRequest(context, moduleName, platform);
};

// lib/sentry.ts turns on neither Sentry's web Session Replay nor its web feedback
// widget. Sentry's own resolvers for its `includeWebReplay: false` and
// `includeWebFeedback: false` options leave both packages out of the bundle.
config.resolver.resolveRequest = withSentryFeedbackResolver(
  withSentryResolver(config, false),
  false,
).resolver.resolveRequest;

// Keep Jest-only tooling out of the app bundle (SDK 52+ handles monorepo resolution;
// avoid extraNodeModules — it can break RN global init with "property is not writable").
config.resolver.blockList = [
  ...(Array.isArray(config.resolver.blockList) ? config.resolver.blockList : []),
  /\/node_modules\/jest\//,
  /\/node_modules\/ts-jest\//,
  /\/lib\/__tests__\//,
];

// The preview WebViews' web libraries (lib/vendor/*.txt: Mermaid, Vega, pdf.js,
// SmilesDrawer, KaTeX CSS) ship as assets, read at run time by lib/vendorAssets.ts,
// instead of as megabytes of strings inside the JS bundle.
config.resolver.assetExts = [...config.resolver.assetExts, "txt"];

// Bind IPv4 so iOS Simulator (127.0.0.1) can reach Metro when ::1-only would fail.
config.server = {
  ...(config.server ?? {}),
  host: "0.0.0.0",
};

module.exports = config;
