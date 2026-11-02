import i18n from "@/lib/i18n";
import { homeGreeting } from "@/features/home/model/homeWelcome";
import fr from "@/lib/i18n/fr.json";

const EN = {
  "chat.home.greeting_morning": "Good morning",
  "chat.home.greeting_morning_name": "Good morning, {{name}}",
  "chat.home.greeting_afternoon": "Good afternoon",
  "chat.home.greeting_afternoon_name": "Good afternoon, {{name}}",
  "chat.home.greeting_evening": "Good evening",
  "chat.home.greeting_evening_name": "Good evening, {{name}}",
  "chat.home.greeting_night": "Hey there",
  "chat.home.greeting_night_name": "Hey there, {{name}}",
};

describe("homeGreeting", () => {
  beforeAll(async () => {
    await i18n.init({ lng: "en", resources: { en: { translation: EN }, fr: { translation: fr } } });
  });

  afterEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("buckets by hour", () => {
    expect(homeGreeting(null, new Date("2026-07-17T09:00:00"))).toBe("Good morning");
    expect(homeGreeting(null, new Date("2026-07-17T14:00:00"))).toBe("Good afternoon");
    expect(homeGreeting(null, new Date("2026-07-17T19:00:00"))).toBe("Good evening");
    expect(homeGreeting(null, new Date("2026-07-17T23:00:00"))).toBe("Hey there");
  });

  it("names the account by its first name", () => {
    expect(homeGreeting("  Sam  Lee ", new Date("2026-07-17T09:00:00"))).toBe("Good morning, Sam");
    expect(homeGreeting("", new Date("2026-07-17T09:00:00"))).toBe("Good morning");
  });

  it("speaks the phone's language, not the server's", async () => {
    await i18n.changeLanguage("fr");
    expect(homeGreeting("Sam", new Date("2026-07-17T19:00:00"))).toBe("Bonsoir, Sam");
  });
});
