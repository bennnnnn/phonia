import type { EmailDraft } from "@/lib/richBlocks";

export function fullEmailText(draft: EmailDraft): string {
  const parts: string[] = [];
  if (draft.to) parts.push(`To: ${draft.to}`);
  if (draft.subject) parts.push(`Subject: ${draft.subject}`);
  if (parts.length) parts.push("");
  parts.push(draft.body);
  return parts.join("\n");
}

/** Gmail web compose — opens Gmail app on mobile when installed. */
export function buildGmailComposeUrl(draft: EmailDraft): string {
  const params = new URLSearchParams({ view: "cm", fs: "1" });
  if (draft.to?.trim()) params.set("to", draft.to.trim());
  if (draft.subject?.trim()) params.set("su", draft.subject.trim());
  if (draft.body.trim()) params.set("body", draft.body.trim());
  return `https://mail.google.com/mail/?${params.toString()}`;
}

/** Gmail iOS/Android app compose deep link. */
export function buildGmailAppComposeUrl(draft: EmailDraft): string {
  const params = new URLSearchParams();
  if (draft.to?.trim()) params.set("to", draft.to.trim());
  if (draft.subject?.trim()) params.set("subject", draft.subject.trim());
  if (draft.body.trim()) params.set("body", draft.body.trim());
  const qs = params.toString();
  return qs ? `googlegmail:///co?${qs}` : "googlegmail:///co";
}

export function gmailComposeCandidates(draft: EmailDraft): string[] {
  return [buildGmailAppComposeUrl(draft), buildGmailComposeUrl(draft)];
}
