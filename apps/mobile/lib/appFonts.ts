/**
 * Every face the app draws with, by the family name its styles use.
 *
 * Android builds embed each face under that same name (the expo-font plugin
 * in app.json; `lib/__tests__/appFonts.test.tsx` keeps the two lists equal),
 * so `useFonts` finds them registered and loads nothing there. iOS and Expo Go
 * register them at launch, behind the splash. iOS stays on runtime loading on
 * purpose: it would find an embedded face by its own family or PostScript
 * name, and React Native then picks the face within that family by the
 * style's weight and slant, which would draw the italic files upright (styles
 * set fontStyle "normal" on them) and react-native-svg's semibold labels
 * regular. The alias a runtime load registers names exactly one face.
 *
 * One file per face: Space Mono and the KaTeX faces Skia also draws come from
 * assets/fonts, the files the plugin embeds.
 */
import type { FontSource } from "expo-font";

import {
  CODE_FONT,
  MATH_FONT,
  MATH_SIZE1_FONT,
  MATH_SYMBOL_FONT,
  MATH_VARIABLE_FONT,
} from "@/lib/fonts";
import { UI_FONT } from "@/lib/uiFont";

export const APP_FONT_FACES: Record<string, FontSource> = {
  [CODE_FONT]: require("@/assets/fonts/SpaceMono-Regular.ttf"),
  [MATH_FONT]: require("@/assets/fonts/KaTeX_Main-Regular.ttf"),
  [MATH_VARIABLE_FONT]: require("@/assets/fonts/KaTeX_Math-Italic.ttf"),
  [MATH_SYMBOL_FONT]: require("@/assets/fonts/KaTeX_AMS-Regular.ttf"),
  // ∬ ∭ ∮ on the math keyboard live only in this face.
  [MATH_SIZE1_FONT]: require("katex/dist/fonts/KaTeX_Size1-Regular.ttf"),
  [UI_FONT.regular]: require("@expo-google-fonts/source-sans-3/400Regular/SourceSans3_400Regular.ttf"),
  [UI_FONT.medium]: require("@expo-google-fonts/source-sans-3/500Medium/SourceSans3_500Medium.ttf"),
  [UI_FONT.semibold]: require("@expo-google-fonts/source-sans-3/600SemiBold/SourceSans3_600SemiBold.ttf"),
  [UI_FONT.bold]: require("@expo-google-fonts/source-sans-3/700Bold/SourceSans3_700Bold.ttf"),
  [UI_FONT.italic]: require("@expo-google-fonts/source-sans-3/400Regular_Italic/SourceSans3_400Regular_Italic.ttf"),
  [UI_FONT.semiboldItalic]: require("@expo-google-fonts/source-sans-3/600SemiBold_Italic/SourceSans3_600SemiBold_Italic.ttf"),
  [UI_FONT.boldItalic]: require("@expo-google-fonts/source-sans-3/700Bold_Italic/SourceSans3_700Bold_Italic.ttf"),
};
