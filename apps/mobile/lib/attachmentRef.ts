const ATTACHMENT_PATH = /\/attachments\/([0-9a-f-]{36})\/file/i;

export function attachmentIdFromRef(ref: string): string | null {
  const match = ref.match(ATTACHMENT_PATH);
  return match?.[1] ?? null;
}
