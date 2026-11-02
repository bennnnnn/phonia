/**
 * Structural guard: a test mocks a shared module only to change what it does.
 *
 * react-i18next was hand-mocked in 95 test files and the component setup's native
 * mocks were repeated 85 times, some copies dropping exports the code reads
 * (code-health audit TEST-07). Every test now gets `__mocks__/react-i18next.ts`,
 * and every component test the mocks in `jest.componentsSetup.js`. A local copy
 * that only restates them drifts from the one place a fix lands; write one only
 * when the test needs other behaviour.
 */

import { appFiles, readSource, relative } from "@/lib/__tests__/support/sourceFiles";

/** Each `jest.mock("<module>", …)` call in `text`, without whitespace or trailing commas. */
function localMocks(text: string, module: string): string[] {
  const opener = `jest.mock("${module}"`;
  const calls: string[] = [];
  for (let start = text.indexOf(opener); start !== -1; start = text.indexOf(opener, start + 1)) {
    let depth = 0;
    for (let i = start + "jest.mock".length; i < text.length; i += 1) {
      if (text[i] === "(") depth += 1;
      else if (text[i] === ")" && --depth === 0) {
        calls.push(text.slice(start, i + 1).replace(/\s+/g, "").replace(/,([}\])])/g, "$1"));
        break;
      }
    }
  }
  return calls;
}

/** `t` answers the key, as the shared mock's does (inline, hoisted to a const, or `mockT`). */
const IDENTITY_I18N = new RegExp(
  "^jest\\.mock\\(\"react-i18next\",\\(\\)=>(?:" +
    "\\(\\{useTranslation:\\(\\)=>\\(\\{t:(?:\\(key(?::string)?\\)=>key|mockT)(?:,i18n:\\{language:\"en\"\\})?\\}\\)\\}\\)" +
    "|\\{constt=\\(key(?::string)?\\)=>key;return\\{useTranslation:\\(\\)=>\\(\\{t\\}\\)\\};?\\})\\)$",
);
const IDENTITY_MOCK_T = /const mockT = \(key(?::\s*string)?\) => key;/;

/** A clipboard function as the setup already stubs it. */
const NO_OP = new Set([
  "jest.fn()",
  "jest.fn().mockResolvedValue(true)",
  "jest.fn(async()=>undefined)",
  "jest.fn(async()=>true)",
  "jest.fn(async()=>\"\")",
  "jest.fn(async()=>false)",
  "jest.fn(async()=>null)",
]);

function restatesSetup(file: string, text: string, module: string, call: string): boolean {
  if (module === "react-i18next") {
    if (!IDENTITY_I18N.test(call)) return false;
    return !call.includes("t:mockT") || (IDENTITY_MOCK_T.test(text) && (text.match(/\bmockT\b/g) ?? []).length === 2);
  }
  // The setup file only loads for component tests.
  if (!file.endsWith(".test.tsx")) return false;
  if (module === "react-native-safe-area-context") {
    const insets = [...call.matchAll(/(?:top|bottom|left|right):(\d+)/g)];
    return insets.length > 0 && insets.every((inset) => inset[1] === "0");
  }
  if (module === "expo-haptics") {
    const read = (source: string) => (source.match(/\b(?:impactAsync|notificationAsync|selectionAsync)\b/g) ?? []).length;
    return read(text.replace(/\s+/g, "")) === read(call);
  }
  const body = /^jest\.mock\("expo-clipboard",\(\)=>\(\{(.*)\}\)\)$/.exec(call)?.[1];
  return body != null && body.split(/,(?=\w+:)/).every((entry) => NO_OP.has(entry.slice(entry.indexOf(":") + 1)));
}

describe("shared test mocks", () => {
  it("no test restates a mock every test already gets", () => {
    const modules = ["react-i18next", "react-native-safe-area-context", "expo-haptics", "expo-clipboard"];
    const copies: string[] = [];
    for (const file of appFiles()) {
      if (!/\.test\.tsx?$/.test(file)) continue;
      const text = readSource(file);
      for (const module of modules) {
        for (const call of localMocks(text, module)) {
          if (restatesSetup(file, text, module, call)) copies.push(`${relative(file)} ${module}`);
        }
      }
    }
    expect(copies).toEqual([]);
  });
});
