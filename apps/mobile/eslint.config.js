// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require("eslint-config-expo/flat");

/**
 * Imports the UI kit replaces. Screens use the kit's component instead, so a
 * feature cannot quietly bring back its own version.
 */
const REPLACED_BY_UI_KIT = [
  {
    name: "@expo/vector-icons",
    message: "Use Icon from @/ui/icons/Icon (Lucide line icons), or BrandMark for logos.",
  },
  {
    name: "@react-native-community/datetimepicker",
    message: "Use TimePickerDialog / DatePickerDialog from @/ui/pickers.",
  },
];

/** Popups live in ui/overlay; everything else asks it for one. Tests may still spy on Alert. */
const POPUPS_OWNED_BY_UI_KIT = [
  {
    name: "react-native",
    importNames: ["Alert"],
    message: "Use confirmDialog / alertDialog from @/ui/overlay/dialogs, or a toast for a passing error.",
  },
  {
    name: "react-native",
    importNames: ["Modal"],
    message: "Use Sheet, Overlay or FullScreenModal from @/ui/overlay.",
  },
];

/** Controls the kit draws itself. ui/ may use them to build its rows. */
const CONTROLS_OWNED_BY_UI_KIT = [
  {
    name: "react-native",
    importNames: ["Switch"],
    message: "Use ListRow with switchValue from @/ui/list/ListRow; the whole row toggles.",
  },
];

const TEST_FILES = ["**/__tests__/**", "**/*.test.ts", "**/*.test.tsx"];

const UI_LEAF = {
  group: ["@/features/*", "@/components/*", "@/contexts/*", "@/hooks/*", "@/app/*"],
  message: "ui/ never imports product code. Pass data and callbacks in as props.",
};

/**
 * lib/math, lib/physics and lib/chemistry are the phone's domain and
 * render-model code: plain data in, plain data out, testable in Node. Screens
 * draw what they return; device adapters live beside their callers.
 */
const DOMAIN_LIB_NO_REACT_NATIVE = [
  {
    name: "react-native",
    message: "Domain libraries stay free of React Native. Put the UI or device part beside its caller.",
  },
];

const DOMAIN_LIB_LEAF = [
  {
    group: ["@/features/*", "@/components/*", "@/app/*", "@/hooks/*", "@/contexts/*"],
    message: "Domain libraries never import product code. Return data; the caller renders it.",
  },
  {
    group: ["expo-*"],
    message: "Domain libraries hold no device code. Put the Expo adapter beside its caller (like lib/clipboard.ts).",
  },
];

/**
 * Domain graphics (math layout, diagrams, plots) and the type scale itself keep raw
 * numbers and colors. Everything else uses lib/type, lib/space, lib/radius,
 * ui/icons/sizes and the theme.
 */
const RAW_DESIGN_VALUES_ALLOWED = [
  "lib/vendor/**",
  "lib/math/**",
  "components/rich/geometry/**",
  "components/rich/FunctionGraphBlock.tsx",
  "components/rich/InteractiveFunctionPlot.tsx",
  "features/chat/components/MathDraftPreview.tsx",
  "lib/graphic.ts",
  // Vega specs for the chart WebView: a pie slice's label is Vega text, not React Native.
  "lib/chartPresentation.ts",
  "lib/type.ts",
];

const DESIGN_TOKEN_RULES = [
  {
    selector: "Property[key.name='fontSize'][value.raw=/^\\d/]",
    message:
      "Use a Type role from lib/type.ts. Raw font sizes belong in that file, or in domain graphics.",
  },
  {
    selector: "Property[key.name='fontWeight']",
    message:
      "Use Weight from lib/type.ts (`...Weight.bold`). It switches to the matching Source Sans file; a bare fontWeight draws fake bold on Android.",
  },
  {
    selector:
      "Property[key.name=/^(padding|margin|gap|paddingHorizontal|paddingVertical|marginHorizontal|marginVertical|paddingTop|paddingBottom|paddingLeft|paddingRight|marginTop|marginBottom|marginLeft|marginRight|rowGap|columnGap)$/][value.raw=/^(?!0$|1$|2$)\\d*\\.?\\d+$/]",
    message: "Use a Space token from lib/space.ts. 0, 1, and 2 may stay raw.",
  },
  {
    selector:
      "Property[key.name=/^(borderRadius|borderTopLeftRadius|borderTopRightRadius|borderBottomLeftRadius|borderBottomRightRadius|borderTopStartRadius|borderTopEndRadius|borderBottomStartRadius|borderBottomEndRadius)$/][value.raw=/^(?!0$|1$|2$)\\d*\\.?\\d+$/]",
    message: "Use a Radius token from lib/radius.ts. 0, 1, and 2 may stay raw.",
  },
  {
    selector:
      "JSXOpeningElement[name.name=/Icon$/] > JSXAttribute[name.name='size'] > JSXExpressionContainer > Literal",
    message: "Use an IconSize from ui/icons/sizes.ts.",
  },
];

/**
 * A color written as a value, wherever it sits: a style key, a JSX prop
 * (`<ActivityIndicator color="#FFFFFF">`, `fill`, `placeholderTextColor`), a
 * module constant or a ternary branch. Named inks and rgb()/hsl() strings
 * count too. A color built in a template string breaks on a token that is
 * already rgba(); use withAlpha.
 */
const RAW_COLOR_RULES = [
  {
    selector: "Literal[value=/^(#([0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})|(rgb|hsl)a?\\(.*)$/]",
    message:
      "Use a theme color (withAlpha for a tint). Neutral shadow ink is SHADOW_COLOR in lib/shadow.ts; palettes are listed in eslint.config.js.",
  },
  {
    selector: "Literal[value=/^(white|black|red|green|blue|gray|grey|silver|yellow|orange|purple|pink)$/i]",
    message: "Use a theme color. A named ink stays the same in dark mode.",
  },
  {
    selector: "TemplateLiteral[quasis.0.value.raw=/^(#[0-9a-fA-F]{0,6}|(rgb|hsl)a?\\(\\s*)$/]",
    message: "Use a theme color, or withAlpha(theme.x, alpha) for a tint.",
  },
  {
    selector: "TemplateLiteral[quasis.length=2][quasis.0.value.raw=''][quasis.1.value.raw=/^[0-9a-fA-F]{2}$/]",
    message: "Use withAlpha(theme.x, alpha). A hex alpha suffix breaks on a token that is already rgba().",
  },
];

/**
 * Every date and time a person reads goes through lib/datetime/format.ts: the app's
 * language, the user's zone, the phone's 12/24-hour setting, a cached formatter. A
 * direct call wrote the phone's locale (a to-do row said "23:30", its editor "11:30 PM")
 * and built a formatter on every call. lib/datetime itself and tests are exempt.
 */
const DATE_FORMAT_MESSAGE =
  "Format dates and times with formatDate (or formatMinuteOfDay, formatCalendarDay, formatTimeZoneName) from @/lib/datetime/format.";
const DATES_FORMATTED_BY_LIB_DATETIME = [
  { object: "Intl", property: "DateTimeFormat", message: DATE_FORMAT_MESSAGE },
  { object: "Intl", property: "RelativeTimeFormat", message: `${DATE_FORMAT_MESSAGE} Add a relative style there.` },
  { property: "toLocaleDateString", message: DATE_FORMAT_MESSAGE },
  { property: "toLocaleTimeString", message: DATE_FORMAT_MESSAGE },
  {
    property: "toLocaleString",
    message: `${DATE_FORMAT_MESSAGE} A number: Intl.NumberFormat in the app's language (lib/money/format.ts).`,
  },
];

/** Palettes and drawn data keep their own colors. */
const RAW_COLORS_ALLOWED = [
  "lib/theme.ts",
  "lib/accent.ts",
  "lib/shadow.ts",
  // Syntax colors, one set per scheme.
  "lib/codeHighlight.ts",
  // Scene data: CPK atom colors, the fluid tint.
  "lib/chemistry/**",
  "lib/physics/**",
  // Light defaults for the document handed to the system browser.
  "lib/preview/openHtmlPreview.ts",
  // Mask luminance: white keeps the shape, black cuts the mark out.
  "ui/icons/custom.tsx",
];

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ["dist/*", "vendor/**", ".expo/**"],
  },
  {
    files: ["**/*.{ts,tsx}"],
    ignores: TEST_FILES,
    rules: {
      "no-restricted-imports": [
        "error",
        { paths: [...REPLACED_BY_UI_KIT, ...POPUPS_OWNED_BY_UI_KIT, ...CONTROLS_OWNED_BY_UI_KIT] },
      ],
      // Import cycles are caught by lib/__tests__/importCycles.test.ts, which,
      // unlike import/no-cycle, also sees type-only imports.
      "@typescript-eslint/no-explicit-any": "error",
    },
  },
  {
    files: ["lib/{math,physics,chemistry}/**/*.{ts,tsx}"],
    ignores: TEST_FILES,
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [...REPLACED_BY_UI_KIT, ...DOMAIN_LIB_NO_REACT_NATIVE],
          patterns: DOMAIN_LIB_LEAF,
        },
      ],
    },
  },
  {
    files: TEST_FILES,
    rules: {
      "no-restricted-imports": ["error", { paths: REPLACED_BY_UI_KIT }],
    },
  },
  {
    // The UI kit is a dependency leaf: tokens and helpers from lib/ only.
    files: ["ui/**/*.{ts,tsx}"],
    ignores: TEST_FILES,
    rules: {
      "no-restricted-imports": [
        "error",
        { paths: [...REPLACED_BY_UI_KIT, ...POPUPS_OWNED_BY_UI_KIT], patterns: [UI_LEAF] },
      ],
    },
  },
  {
    // The one place that may open a native Modal or Alert.
    files: ["ui/overlay/**/*.{ts,tsx}"],
    ignores: TEST_FILES,
    rules: {
      "no-restricted-imports": ["error", { paths: REPLACED_BY_UI_KIT, patterns: [UI_LEAF] }],
    },
  },
  {
    rules: {
      // Expo SDK 56 enables React Compiler hook rules that flag common RN patterns.
      "react-hooks/refs": "off",
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/preserve-manual-memoization": "off",
      "react/no-unescaped-entities": "off",
    },
  },
  {
    // The chat turn is a reducer held outside render (code-health audit CLAR-04): chat
    // code reads refs in callbacks and effects only, never while rendering.
    files: ["features/chat/**/*.{ts,tsx}"],
    ignores: TEST_FILES,
    rules: {
      "react-hooks/refs": "error",
    },
  },
  {
    files: ["**/*.{ts,tsx}"],
    ignores: [...TEST_FILES, "lib/datetime/**"],
    rules: { "no-restricted-properties": ["error", ...DATES_FORMATTED_BY_LIB_DATETIME] },
  },
  {
    files: ["**/*.{ts,tsx}"],
    ignores: [...TEST_FILES, ...RAW_DESIGN_VALUES_ALLOWED],
    rules: { "no-restricted-syntax": ["error", ...DESIGN_TOKEN_RULES, ...RAW_COLOR_RULES] },
  },
  {
    // Palettes keep their colors and still take the size, spacing and radius tokens.
    files: RAW_COLORS_ALLOWED,
    ignores: [...TEST_FILES, ...RAW_DESIGN_VALUES_ALLOWED],
    rules: { "no-restricted-syntax": ["error", ...DESIGN_TOKEN_RULES] },
  },
]);
