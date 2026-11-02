import {
  AI_CONSENT_ITEMS,
  aiConsentRedirect,
  needsAiDataConsent,
} from "@/features/auth/model/aiConsent";
import en from "@/lib/i18n/en.json";

describe("needsAiDataConsent", () => {
  it("asks a signed-in account the server says has not agreed", () => {
    expect(needsAiDataConsent({ ai_data_consent_at: null })).toBe(true);
  });

  it("lets an account that agreed through", () => {
    expect(needsAiDataConsent({ ai_data_consent_at: "2026-10-19T12:00:00Z" })).toBe(false);
  });

  it("lets an unknown answer through (older server or an old cold-start cache)", () => {
    expect(needsAiDataConsent({})).toBe(false);
    expect(needsAiDataConsent({ ai_data_consent_at: undefined })).toBe(false);
  });

  it("never asks while signed out", () => {
    expect(needsAiDataConsent(null)).toBe(false);
    expect(needsAiDataConsent(undefined)).toBe(false);
  });
});

describe("aiConsentRedirect", () => {
  const notYet = { ai_data_consent_at: null };

  it.each(["/", "/todos", "/settings/data-controls", "/memory", "/gallery"])(
    "sends an account that has not agreed from %s to the consent screen",
    (pathname) => {
      expect(aiConsentRedirect(notYet, pathname)).toBe("/consent");
    },
  );

  it.each(["/consent", "/login", "/onboarding"])("leaves %s alone", (pathname) => {
    expect(aiConsentRedirect(notYet, pathname)).toBeNull();
  });

  it("never redirects an account that agreed, an unknown answer or a signed-out user", () => {
    expect(aiConsentRedirect({ ai_data_consent_at: "2026-10-19T12:00:00Z" }, "/")).toBeNull();
    expect(aiConsentRedirect({}, "/")).toBeNull();
    expect(aiConsentRedirect(null, "/")).toBeNull();
  });
});

describe("AI_CONSENT_ITEMS", () => {
  const strings = en as Record<string, string>;

  it("has English copy for every item", () => {
    for (const item of AI_CONSENT_ITEMS) {
      expect(strings[item.titleKey]).toBeTruthy();
      expect(strings[item.bodyKey]).toBeTruthy();
    }
  });

  it("names every outside service the privacy policy lists for chat, photos, voice and search", () => {
    const copy = AI_CONSENT_ITEMS.map((item) => strings[item.bodyKey]).join(" ");
    for (const name of ["OpenRouter", "OpenAI", "Mathpix", "Tavily", "public search engines"]) {
      expect(copy).toContain(name);
    }
  });
});
