import { Platform, Share } from "react-native";

import { isShareCancelled } from "@/lib/shareCancelled";

/** Open the OS share sheet (Messages, Mail, Files, …). */
export async function presentShareSheet(options: {
  message: string;
  title?: string | null;
}): Promise<void> {
  const message = options.message.trim();
  if (!message) {
    throw new Error("share_empty");
  }
  const title = options.title?.trim() || undefined;
  try {
    await Share.share(
      { message, ...(title ? { title } : {}) },
      Platform.OS === "ios"
        ? { subject: title }
        : { dialogTitle: title },
    );
  } catch (error) {
    if (isShareCancelled(error)) return;
    throw error;
  }
}
