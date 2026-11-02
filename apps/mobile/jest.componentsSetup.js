const { jest: jestGlobals } = require("@jest/globals");

/**
 * Sheet (and other chrome) import RNGH + Reanimated. The RN jest env has
 * neither native module, so mock them before any component test file loads.
 */
jestGlobals.mock("react-native-reanimated", () => {
  const React = require("react");
  const { View: RNView } = require("react-native");
  const id = (value) => value;
  /**
   * Spread `animatedProps` onto the wrapped component instead of dropping it.
   * Paired with the synchronous `useAnimatedProps` below, the worklet's derived
   * values arrive as ordinary props, so a test can assert an animated SVG
   * element's geometry the same way it asserts a static one.
   */
  const createAnimatedComponent = (Component) => {
    const Animated = ({ animatedProps, ...rest }) =>
      React.createElement(Component, { ...rest, ...(animatedProps ?? {}) });
    Animated.displayName = `Animated(${Component.displayName ?? Component.name ?? "Component"})`;
    return Animated;
  };
  const layoutAnim = () => {
    const api = {};
    api.duration = () => api;
    api.easing = () => api;
    api.delay = () => api;
    api.springify = () => api;
    api.damping = () => api;
    api.stiffness = () => api;
    return api;
  };
  return {
    __esModule: true,
    default: { View: RNView, createAnimatedComponent },
    createAnimatedComponent,
    Easing: {
      linear: id,
      ease: id,
      sin: id,
      cubic: id,
      inOut: () => id,
      out: () => id,
      in: () => id,
    },
    runOnJS: (fn) => fn,
    runOnUI: (fn) => (...args) => fn(...args),
    useAnimatedKeyboard: () => ({ height: { value: 0 }, state: { value: 0 } }),
    useAnimatedStyle: (factory) => (typeof factory === "function" ? factory() : {}),
    useAnimatedProps: (factory) => (typeof factory === "function" ? factory() : {}),
    // Evaluate once so tests see the initial derived value (no UI thread here).
    useDerivedValue: (factory) => ({
      value: typeof factory === "function" ? factory() : undefined,
    }),
    useAnimatedReaction: () => undefined,
    // Reanimated keeps one shared-value object for the lifetime of a component.
    // Preserve that identity so a React state update does not look like a fresh
    // animation mount and retrigger effects in component tests.
    // ``get``/``set`` as Reanimated 4 has them, for code that writes outside a worklet.
    useSharedValue: (value) =>
      React.useRef({
        value,
        get() {
          return this.value;
        },
        set(next) {
          this.value = typeof next === "function" ? next(this.value) : next;
        },
      }).current,
    withSpring: id,
    withTiming: id,
    withRepeat: id,
    withSequence: id,
    withDelay: id,
    cancelAnimation: jestGlobals.fn(),
    SlideInRight: layoutAnim(),
    SlideOutLeft: layoutAnim(),
    SlideOutDown: layoutAnim(),
  };
});

jestGlobals.mock("react-native-gesture-handler", () => {
  const { View: RNView, Pressable: RNPressable } = require("react-native");
  const chain = () => {
    const api = new Proxy(
      {},
      {
        get: (_target, prop) => {
          if (prop === "then") return undefined;
          return () => api;
        },
      },
    );
    return api;
  };
  return {
    Gesture: {
      Pan: () => chain(),
      Pinch: () => chain(),
      Tap: () => chain(),
      LongPress: () => chain(),
      Simultaneous: () => chain(),
      Race: () => chain(),
      Exclusive: () => chain(),
    },
    GestureDetector: ({ children }) => children,
    GestureHandlerRootView: RNView,
    Pressable: RNPressable,
    ScrollView: require("react-native").ScrollView,
    Swipeable: RNView,
  };
});

// expo-constants pulls expo-modules-core's native EventEmitter in this env.
// Standalone (not Expo Go) so native-module gates probe their module mock.
// Screens render without a SafeAreaProvider in tests. The library's own mock
// reports zero insets there; files that mock the module themselves still win.
jestGlobals.mock("react-native-safe-area-context", () =>
  require("react-native-safe-area-context/jest/mock").default,
);

jestGlobals.mock("expo-constants", () => ({
  __esModule: true,
  default: { executionEnvironment: "standalone", appOwnership: null },
  ExecutionEnvironment: { Bare: "bare", Standalone: "standalone", StoreClient: "storeClient" },
}));

// expo-haptics is a native module (expo-modules-core EventEmitter) that cannot
// load in this env; lib/haptics is imported by shared chrome like
// SheetFormHeader and SettingsSwitchRow.
jestGlobals.mock("expo-haptics", () => ({
  impactAsync: () => Promise.resolve(),
  notificationAsync: () => Promise.resolve(),
  selectionAsync: () => Promise.resolve(),
  performAndroidHapticsAsync: () => Promise.resolve(),
  ImpactFeedbackStyle: { Light: "light", Medium: "medium", Heavy: "heavy" },
  NotificationFeedbackType: { Success: "success", Warning: "warning", Error: "error" },
  AndroidHaptics: {
    Confirm: "confirm",
    Reject: "reject",
    Clock_Tick: "clock-tick",
    Long_Press: "long-press",
    Virtual_Key: "virtual-key",
    Segment_Tick: "segment-tick",
  },
}));

// expo-clipboard is a native module (expo-modules-core EventEmitter) that
// cannot load here; the share sheet renders in the chat screen and drawer.
// Tests that check copying mock it themselves.
jestGlobals.mock("expo-clipboard", () => ({
  setStringAsync: jestGlobals.fn(async () => true),
  getStringAsync: jestGlobals.fn(async () => ""),
  hasStringAsync: jestGlobals.fn(async () => false),
  getImageAsync: jestGlobals.fn(async () => null),
  hasImageAsync: jestGlobals.fn(async () => false),
}));

// expo-asset and expo-crypto are native modules (expo-modules-core) that cannot
// load here; rich blocks reach them through lib/preview/previewPageFile.ts and
// lib/vendorAssets.ts. Nothing is read or hashed: a test that shows a preview
// page mocks lib/preview/previewPageFile.
jestGlobals.mock("expo-asset", () => ({
  Asset: {
    fromModule: () => ({
      hash: null,
      downloadAsync: () => Promise.reject(new Error("No assets in this environment")),
    }),
  },
}));

jestGlobals.mock("expo-crypto", () => ({
  CryptoDigestAlgorithm: { SHA256: "SHA-256" },
  digestStringAsync: () => Promise.reject(new Error("No digests in this environment")),
  randomUUID: () => "00000000-0000-4000-8000-000000000000",
}));

// expo-image's Image is a native view (requireNativeViewManager) that cannot
// load here. Wrap RN's Image and translate the load event into expo-image's
// shape ({ source } instead of { nativeEvent: { source } }) so components
// under test see the real contract.
jestGlobals.mock("expo-image", () => {
  const React = require("react");
  const { Image: RNImage } = require("react-native");
  const Image = React.forwardRef(
    ({ onLoad, contentFit, cachePolicy, transition, ...rest }, ref) =>
      React.createElement(RNImage, {
        ...rest,
        ref,
        resizeMode: contentFit,
        contentFit,
        cachePolicy,
        transition,
        onLoad: onLoad
          ? (event) => onLoad({ source: event?.nativeEvent?.source ?? {} })
          : undefined,
      }),
  );
  Image.displayName = "ExpoImageMock";
  return { Image };
});

// expo-linear-gradient is a native view (expo-modules-core) that cannot load
// here; markdown tables fade their clipped edge with it, so every reply render
// reaches it. A plain View keeps the gradient's props for assertions.
jestGlobals.mock("expo-linear-gradient", () => {
  const React = require("react");
  const { View } = require("react-native");
  const LinearGradient = (props) => React.createElement(View, props);
  return { LinearGradient };
});
