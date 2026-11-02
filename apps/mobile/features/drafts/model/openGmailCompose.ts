import * as Clipboard from "expo-clipboard";
import { Linking } from "react-native";

import { fullEmailText, gmailComposeCandidates } from "@/features/drafts/model/emailCompose";
import type { EmailDraft } from "@/lib/richBlocks";

type GmailOpenResult = "app" | "web" | "copied_only";

async function tryOpenUrl(url: string): Promise<boolean> {
  try {
    await Linking.openURL(url);
    return true;
  } catch {
    return false;
  }
}

/** Copy draft, then open Gmail compose (app first, web fallback). */
export async function openGmailCompose(draft: EmailDraft): Promise<GmailOpenResult> {
  await Clipboard.setStringAsync(fullEmailText(draft));

  const [appUrl, webUrl] = gmailComposeCandidates(draft);
  if (await tryOpenUrl(appUrl)) return "app";
  if (await tryOpenUrl(webUrl)) return "web";
  return "copied_only";
}
