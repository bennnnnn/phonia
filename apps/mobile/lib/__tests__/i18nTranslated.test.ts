/**
 * Structural guard: every locale says each string in its own language (code-health audit CLAR-09).
 *
 * Key parity passed while about 47 strings per locale (75 in Amharic) were still English:
 * permission prompts, delete confirmations and error toasts showed in English inside a
 * German or Amharic app, and new keys arrived in English in every file at once. A value
 * may equal English only when it is a name or a symbol every language keeps, or a word
 * the language spells the same; both lists are below. Every value also keeps English's
 * `{{placeholders}}`, which a translation that drops one would break.
 */

import en from "@/lib/i18n/en.json";
import am from "@/lib/i18n/am.json";
import de from "@/lib/i18n/de.json";
import es from "@/lib/i18n/es.json";
import fr from "@/lib/i18n/fr.json";
import itLocale from "@/lib/i18n/it.json";
import pt from "@/lib/i18n/pt.json";
import ru from "@/lib/i18n/ru.json";
import tr from "@/lib/i18n/tr.json";

const LOCALES = { am, de, es, fr, it: itLocale, pt, ru, tr } as const;
type Locale = keyof typeof LOCALES;
type Bundle = Record<string, string>;
const EN = en as Bundle;

/** Names and symbols every language keeps as they are. */
const KEPT_EVERYWHERE = new Set([
  "app.name", // the product
  "plans.plus", // plan names, as the stores show them
  "plans.pro",
  "settings.sign_in_apple", // sign-in providers
  "settings.sign_in_google",
  "settings.sign_in_dev", // development builds only
  "chat.live_talk_a11y", // Live talk is the feature's name in every locale
  "settings.live_talk_minutes",
  "upgrade.feature_live_talk_plain",
  "share.action_pdf", // file format
  "share.attachment_pdf",
  "common.ok",
  "chat.math_converter_clear", // the calculator's AC key
  "chat.math_keyboard_abc", // the key back to letters
  "chat.math_keyboard_group_trig", // trig function keys
  "rich.chemistry_ph_value", // the pH symbol
  "rich.graph_expr_placeholder", // a formula
]);

/** Words each language spells as English does: a match is the translation. */
const SAME_WORD: Record<Locale, readonly string[]> = {
  am: [],
  de: [
    "chat.quota_nudge_cta", // Upgrade
    "memory.details_label",
    "picker.minute",
    "preview.code_tab",
    "rich.array_index",
    "rich.callout_info",
    "rich.chemistry_anchor_start",
    "rich.chemistry_anode",
    "rich.chemistry_element",
    "rich.chemistry_ideal_angle",
    "rich.chemistry_scene_titration",
    "rich.simulation_title",
    "settings.about_version",
    "settings.accent_indigo",
    "settings.appearance_system",
    "settings.chat",
    "settings.chats_group",
    "settings.name_label",
    "share.default_title",
  ],
  es: [
    "chat.math_converter_cat_amount", // Moles
    "rich.callout_info",
    "rich.chemistry_ideal_angle",
    "settings.chat",
    "settings.chats_group",
    "settings.legal",
    "settings.plan_label",
    "share.default_title",
    "todos.category_personal",
  ],
  fr: [
    "chat.attach_photo",
    "chat.math_converter_cat_amount", // Moles
    "chat.math_converter_cat_angle",
    "chat.math_converter_cat_charge",
    "chat.math_converter_cat_force",
    "chat.math_converter_cat_volume",
    "chat.math_scan_subject_math", // Maths
    "chat.sources_count_one",
    "chat.sources_count_other",
    "chat.sources_title",
    "picker.minute",
    "preview.code_tab",
    "rich.callout_important",
    "rich.callout_info",
    "rich.callout_note",
    "rich.chemistry_anode",
    "rich.chemistry_cathode",
    "rich.chemistry_charge",
    "rich.chemistry_initial",
    "rich.diagram_title_circuit",
    "rich.scene_title_collision",
    "rich.scene_title_forces",
    "rich.scene_title_moments",
    "rich.scene_title_projectile",
    "rich.simulation_title",
    "rich.source",
    "settings.about_version",
    "settings.accent_graphite",
    "settings.accent_indigo",
    "settings.accent_violet",
    "settings.assistant",
    "settings.notifications",
    "share.role_assistant",
    "todos.date_label",
  ],
  it: [
    "chat.attach_file",
    "chat.math_converter_cat_area",
    "chat.math_converter_cat_volume",
    "login.privacy",
    "rich.area",
    "rich.callout_info",
    "settings.account",
    "settings.chat",
    "settings.email",
    "settings.emoji",
    "share.default_title",
  ],
  pt: [
    "chat.math_converter_cat_volume",
    "rich.callout_info",
    "rich.chemistry_ideal_angle",
    "rich.diagram_part_capacitor",
    "rich.diagram_part_resistor",
    "settings.chat",
    "settings.chats_group",
    "share.default_title",
  ],
  ru: [],
  tr: [
    "rich.chemistry_element",
    "rich.chemistry_ideal_angle",
    "settings.emoji",
    "settings.plan_label",
  ],
};

const PLACEHOLDER = /\{\{\s*([^}\s]+)\s*\}\}/g;

function placeholders(value: string): string[] {
  return [...value.matchAll(PLACEHOLDER)].map((match) => match[1] ?? "").sort();
}

/** Text a reader sees, placeholders left out: "{{percent}}%" has none. */
function hasWords(value: string): boolean {
  return /\p{L}{2}/u.test(value.replace(PLACEHOLDER, ""));
}

/** Keys whose value in `bundle` is still English and not an allowed match. */
function untranslated(code: Locale, bundle: Bundle): string[] {
  const allowed = new Set(SAME_WORD[code]);
  return Object.entries(EN)
    .filter(([key, value]) => bundle[key] === value && hasWords(value))
    .filter(([key]) => !KEPT_EVERYWHERE.has(key) && !allowed.has(key))
    .map(([key]) => key);
}

describe("i18n translations", () => {
  it("sees an English value and a dropped placeholder", () => {
    expect(untranslated("de", { "chat.stop": "Stop", "app.name": "Recall" })).toEqual(["chat.stop"]);
    expect(placeholders("Open PDF {{fileName}}")).toEqual(["fileName"]);
    expect(hasWords("{{status}}, {{percent}}")).toBe(false);
  });

  for (const [code, bundle] of Object.entries(LOCALES) as [Locale, Bundle][]) {
    it(`${code}.json says every string in its own language`, () => {
      expect(untranslated(code, bundle)).toEqual([]);
    });

    it(`${code}.json keeps every placeholder English has`, () => {
      const broken = Object.entries(EN)
        .filter(([key, value]) => placeholders(value).join() !== placeholders(bundle[key] ?? "").join())
        .map(([key]) => key);
      expect(broken).toEqual([]);
    });

    it(`${code}.json allows only words it still spells as English does`, () => {
      const stale = SAME_WORD[code].filter((key) => bundle[key] !== EN[key]);
      expect(stale).toEqual([]);
    });
  }

  it("keeps only names and symbols English still has", () => {
    expect([...KEPT_EVERYWHERE].filter((key) => !(key in EN))).toEqual([]);
  });
});
