import js from "@eslint/js";
import tsParser from "@typescript-eslint/parser";
import tsPlugin from "@typescript-eslint/eslint-plugin";

// Flat config for ESLint 9. Slice 1 keeps a minimal, strict-by-default setup.
export default [
  js.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}", "vite.config.ts"],
    languageOptions: {
      parser: tsParser,
      parserOptions: { ecmaVersion: 2022, sourceType: "module" },
      globals: {
      // Browser + Vite env globals.
      },
      ecmaVersion: 2022,
      sourceType: "module",
    },
    plugins: { "@typescript-eslint": tsPlugin },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_" },
      ],
      "no-empty": ["error", { allowEmptyCatch: true }],
      // `no-undef` doesn't understand TS lib / DOM / Node globals — TS itself
      // catches undefined references, so disable it for TS files.
      "no-undef": "off",
    },
  },
  {
    // Browser globals for app code.
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      globals: {
        window: "readonly",
        document: "readonly",
        console: "readonly",
        sessionStorage: "readonly",
        localStorage: "readonly",
        AbortController: "readonly",
        fetch: "readonly",
        TextDecoder: "readonly",
        ReadableStream: "readonly",
        URL: "readonly",
        URLSearchParams: "readonly",
        HTMLElement: "readonly",
        HTMLDivElement: "readonly",
        HTMLInputElement: "readonly",
        HTMLFormElement: "readonly",
        React: "readonly",
        Node: "readonly",
        Element: "readonly",
        Event: "readonly",
        FormData: "readonly",
        Intl: "readonly",
        Date: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        import: "readonly",
      },
    },
  },
  {
    ignores: ["dist/**", "node_modules/**", "*.cjs"],
  },
];
