import type { ExpoConfig } from "expo/config";

import appConfig from "../../app.config";
import appJson from "../../app.json";

/**
 * Store-review guards on app.json. Expo decides the order its config plugins write
 * Info.plist in, so every plugin that writes a usage description must carry the text
 * in ios.infoPlist, or whichever plugin happens to run last replaces it.
 */
const USAGE_DESCRIPTION_OPTIONS: Record<string, Record<string, string>> = {
  "expo-location": {
    locationWhenInUsePermission: "NSLocationWhenInUseUsageDescription",
    motionUsagePermission: "NSMotionUsageDescription",
  },
  "expo-image-picker": {
    photosPermission: "NSPhotoLibraryUsageDescription",
    cameraPermission: "NSCameraUsageDescription",
    microphonePermission: "NSMicrophoneUsageDescription",
  },
  "expo-media-library": {
    photosPermission: "NSPhotoLibraryUsageDescription",
    savePhotosPermission: "NSPhotoLibraryAddUsageDescription",
  },
  "expo-audio": {
    microphonePermission: "NSMicrophoneUsageDescription",
  },
  "@config-plugins/react-native-webrtc": {
    cameraPermission: "NSCameraUsageDescription",
    microphonePermission: "NSMicrophoneUsageDescription",
  },
};

function pluginOptions(name: string): Map<string, unknown> {
  const plugins: readonly unknown[] = appJson.expo.plugins;
  for (const entry of plugins) {
    if (Array.isArray(entry) && entry[0] === name) {
      return new Map(Object.entries(entry[1] ?? {}));
    }
  }
  throw new Error(`app.json has no options for ${name}`);
}

const infoPlist = new Map<string, unknown>(Object.entries(appJson.expo.ios.infoPlist));

describe("app store config", () => {
  it.each(Object.entries(USAGE_DESCRIPTION_OPTIONS))(
    "%s writes the same usage descriptions as ios.infoPlist",
    (plugin, options) => {
      const configured = pluginOptions(plugin);
      for (const [option, key] of Object.entries(options)) {
        expect(infoPlist.get(key)).toEqual(expect.any(String));
        expect({ [option]: configured.get(option) }).toEqual({ [option]: infoPlist.get(key) });
      }
    },
  );

  it("leaves out permissions the app never asks for", () => {
    expect(pluginOptions("expo-secure-store").get("faceIDPermission")).toBe(false);
    const location = pluginOptions("expo-location");
    expect(location.get("locationAlwaysPermission")).toBe(false);
    expect(location.get("locationAlwaysAndWhenInUsePermission")).toBe(false);
    for (const key of [
      "NSFaceIDUsageDescription",
      "NSLocationAlwaysUsageDescription",
      "NSLocationAlwaysAndWhenInUseUsageDescription",
    ]) {
      expect(infoPlist.has(key)).toBe(false);
    }
  });

  it("never plays audio in the background", () => {
    // Read-aloud stops and Live Talk hangs up when the app leaves the foreground.
    expect(pluginOptions("expo-audio").get("enableBackgroundPlayback")).toBe(false);
    expect(infoPlist.has("UIBackgroundModes")).toBe(false);
    expect(appJson.expo.android.blockedPermissions).toEqual(
      expect.arrayContaining([
        "android.permission.FOREGROUND_SERVICE",
        "android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK",
      ]),
    );
  });

  it("asks Android for no media read access", () => {
    // Saving to the gallery is write-only and the photo picker needs no permission.
    expect(pluginOptions("expo-media-library").get("granularPermissions")).toEqual([]);
    expect(appJson.expo.android.blockedPermissions).toEqual(
      expect.arrayContaining([
        "android.permission.READ_MEDIA_IMAGES",
        "android.permission.READ_MEDIA_VIDEO",
        "android.permission.READ_MEDIA_AUDIO",
        "android.permission.READ_MEDIA_VISUAL_USER_SELECTED",
      ]),
    );
  });

  it("declares HTTPS-only encryption for export compliance", () => {
    expect(appJson.expo.ios.config.usesNonExemptEncryption).toBe(false);
  });
});

/**
 * The iOS privacy manifest: `ios.privacyManifests` in app.json, which `expo prebuild` writes to
 * ios/Recall/PrivacyInfo.xcprivacy. One row per Apple data type the app collects, each checked
 * against the code; docs/PRODUCTION.md (Store submission) gives the same rows as the App Store
 * Connect answers. A change to what the app sends changes this table, app.json and that list.
 */
const COLLECTED_DATA: Record<string, { linked: boolean; purposes: readonly string[] }> = {
  // Google or Apple sign-in; reminder and account emails.
  EmailAddress: { linked: true, purposes: ["AppFunctionality"] },
  // Sign-in and profile name; the greeting and the model's answers use it.
  Name: { linked: true, purposes: ["AppFunctionality", "ProductPersonalization"] },
  // The account id: RevenueCat's app user id, and the owner of each product event.
  UserID: { linked: true, purposes: ["AppFunctionality", "Analytics"] },
  // This install's id (lib/installationId.ts), sent with the push token and product events.
  DeviceID: { linked: true, purposes: ["AppFunctionality", "Analytics"] },
  // A nearby or "where am I" message carries the fix's coordinates (features/chat/model/clientGeo.ts), and its
  // place label is the coordinates to four decimals when the phone finds no place name.
  PreciseLocation: { linked: true, purposes: ["AppFunctionality"] },
  // The city, region and country saved while Use current location is on.
  CoarseLocation: { linked: true, purposes: ["AppFunctionality"] },
  // Attached photos, maths scans and the profile photo.
  PhotosorVideos: { linked: true, purposes: ["AppFunctionality"] },
  // Voice input and Live Talk.
  AudioData: { linked: true, purposes: ["AppFunctionality"] },
  // Messages, chats, memory, to-dos, attached files, custom instructions and feedback.
  OtherUserContent: { linked: true, purposes: ["AppFunctionality", "ProductPersonalization"] },
  // The optional profile fields (age, country, job) and each session's device name or model.
  OtherDataTypes: { linked: true, purposes: ["AppFunctionality", "ProductPersonalization"] },
  // Plan and subscription status (RevenueCat), and the purchase outcome events.
  PurchaseHistory: { linked: true, purposes: ["AppFunctionality", "Analytics"] },
  // Metadata-only product events (lib/productAnalytics.ts).
  ProductInteraction: { linked: true, purposes: ["Analytics"] },
  // How quickly replies start (`chat_ttft` buckets), and Sentry's traces when a DSN is set.
  PerformanceData: { linked: true, purposes: ["Analytics", "AppFunctionality"] },
  // Sentry, when EXPO_PUBLIC_SENTRY_DSN is set: no user and no message text (lib/sentry.ts).
  CrashData: { linked: false, purposes: ["AppFunctionality"] },
  OtherDiagnosticData: { linked: false, purposes: ["AppFunctionality"] },
};

/**
 * Required-reason APIs the app's own code reaches, with Apple's reasons. Each SDK declares its
 * own in its manifest, and `pod install` adds those to the app's (React Native's privacy
 * manifest aggregation), so only the app's own use belongs here.
 */
const ACCESSED_APIS: Record<string, readonly string[]> = {
  // Modification times and sizes of the app's own cache and document files, read through
  // expo-file-system's getInfoAsync, whose manifest gives only the SDK wrapper reason (0A2A.1).
  FileTimestamp: ["C617.1"],
};

// Apple's identifiers, from developer.apple.com/documentation/bundleresources/app-privacy-configuration.
const DATA_TYPE_PREFIX = "NSPrivacyCollectedDataType";
const PURPOSE_PREFIX = "NSPrivacyCollectedDataTypePurpose";
const API_CATEGORY_PREFIX = "NSPrivacyAccessedAPICategory";
const APPLE_DATA_TYPES: ReadonlySet<string> = new Set([
  "Name", "EmailAddress", "PhoneNumber", "PhysicalAddress", "OtherUserContactInfo",
  "Health", "Fitness",
  "PaymentInfo", "CreditInfo", "OtherFinancialInfo",
  "PreciseLocation", "CoarseLocation",
  "SensitiveInfo", "Contacts",
  "EmailsOrTextMessages", "PhotosorVideos", "AudioData", "GameplayContent", "CustomerSupport",
  "OtherUserContent",
  "BrowsingHistory", "SearchHistory",
  "UserID", "DeviceID",
  "PurchaseHistory",
  "ProductInteraction", "AdvertisingData", "OtherUsageData",
  "CrashData", "PerformanceData", "OtherDiagnosticData",
  "EnvironmentScanning", "Hands", "Head",
  "OtherDataTypes",
]);
const APPLE_PURPOSES: ReadonlySet<string> = new Set([
  "ThirdPartyAdvertising", "DeveloperAdvertising", "Analytics", "ProductPersonalization",
  "AppFunctionality", "Other",
]);
const APPLE_API_REASONS: Record<string, readonly string[]> = {
  FileTimestamp: ["DDA9.1", "C617.1", "3B52.1", "0A2A.1"],
  SystemBootTime: ["35F9.1", "8FFB.1", "3D61.1"],
  DiskSpace: ["85F4.1", "E174.1", "7D9E.1", "B728.1"],
  ActiveKeyboards: ["3EC4.1", "54BD.1"],
  UserDefaults: ["CA92.1", "1C8F.1", "C56D.1", "AC6B.1"],
};
const ENTRY_KEYS = [
  "NSPrivacyCollectedDataType",
  "NSPrivacyCollectedDataTypeLinked",
  "NSPrivacyCollectedDataTypePurposes",
  "NSPrivacyCollectedDataTypeTracking",
];

/** Apple's identifier without its prefix, or null when it does not carry the prefix. */
function unprefixed(id: string, prefix: string): string | null {
  return id.startsWith(prefix) ? id.slice(prefix.length) : null;
}

// Typed as Expo reads it, so a misspelt key or a wrong value type fails the typecheck.
const iosConfig: NonNullable<ExpoConfig["ios"]> = appJson.expo.ios;
const manifest = iosConfig.privacyManifests;
const collected = manifest?.NSPrivacyCollectedDataTypes ?? [];
const accessed = manifest?.NSPrivacyAccessedAPITypes ?? [];

describe("iOS privacy manifest", () => {
  it("declares each data type the app collects, linked and for what", () => {
    const declared: Record<string, { linked: boolean; purposes: string[] }> = {};
    for (const entry of collected) {
      const id = entry.NSPrivacyCollectedDataType;
      declared[unprefixed(id, DATA_TYPE_PREFIX) ?? id] = {
        linked: entry.NSPrivacyCollectedDataTypeLinked,
        purposes: entry.NSPrivacyCollectedDataTypePurposes
          .map((purpose) => unprefixed(purpose, PURPOSE_PREFIX) ?? purpose)
          .sort(),
      };
    }
    const expected: Record<string, { linked: boolean; purposes: string[] }> = {};
    for (const [type, { linked, purposes }] of Object.entries(COLLECTED_DATA)) {
      expected[type] = { linked, purposes: [...purposes].sort() };
    }
    expect(declared).toEqual(expected);
    expect(collected).toHaveLength(Object.keys(COLLECTED_DATA).length);
  });

  it("writes every collected type in Apple's shape, none for tracking", () => {
    expect(collected.length).toBeGreaterThan(0);
    const problems: string[] = [];
    const seen = new Set<string>();
    for (const entry of collected) {
      const id = entry.NSPrivacyCollectedDataType;
      const type = unprefixed(id, DATA_TYPE_PREFIX);
      if (type === null || !APPLE_DATA_TYPES.has(type)) problems.push(`${id}: not an Apple data type`);
      if (seen.has(id)) problems.push(`${id}: declared twice`);
      seen.add(id);
      if (Object.keys(entry).sort().join() !== ENTRY_KEYS.join()) problems.push(`${id}: keys`);
      if (typeof entry.NSPrivacyCollectedDataTypeLinked !== "boolean") problems.push(`${id}: Linked`);
      if (entry.NSPrivacyCollectedDataTypeTracking !== false) problems.push(`${id}: Tracking`);
      const purposes = entry.NSPrivacyCollectedDataTypePurposes;
      if (purposes.length === 0 || new Set(purposes).size !== purposes.length) {
        problems.push(`${id}: purposes`);
      }
      for (const purpose of purposes) {
        const name = unprefixed(purpose, PURPOSE_PREFIX);
        if (name === null || !APPLE_PURPOSES.has(name)) problems.push(`${id}: ${purpose}`);
      }
    }
    expect(problems).toEqual([]);
    expect(manifest?.NSPrivacyTracking).toBe(false);
    expect(manifest?.NSPrivacyTrackingDomains ?? []).toEqual([]);
  });

  it("gives Apple's reason for each required-reason API the app's own code calls", () => {
    const declared: Record<string, readonly string[]> = {};
    const problems: string[] = [];
    for (const api of accessed) {
      const id = api.NSPrivacyAccessedAPIType;
      const category = unprefixed(id, API_CATEGORY_PREFIX) ?? id;
      const reasons = api.NSPrivacyAccessedAPITypeReasons;
      declared[category] = reasons;
      const allowed = APPLE_API_REASONS[category];
      if (!allowed) problems.push(`${id}: not an Apple API category`);
      for (const reason of reasons) {
        if (!allowed?.includes(reason)) problems.push(`${id}: ${reason} is not one of its reasons`);
      }
      if (reasons.length === 0 || new Set(reasons).size !== reasons.length) {
        problems.push(`${id}: reasons`);
      }
    }
    expect(problems).toEqual([]);
    expect(declared).toEqual(ACCESSED_APIS);
    expect(accessed).toHaveLength(Object.keys(ACCESSED_APIS).length);
  });

  it("reaches the native build through app.config.ts", () => {
    const resolved = appConfig({
      projectRoot: "",
      staticConfigPath: null,
      packageJsonPath: null,
      config: {},
    });
    expect(manifest).toBeDefined();
    expect(resolved.ios?.privacyManifests).toEqual(manifest);
  });
});
