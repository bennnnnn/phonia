/** UUID v4-shaped ids minted by the API (not `streaming` / `local-*`). */
const SERVER_MESSAGE_ID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isServerMessageId(id: string): boolean {
  return SERVER_MESSAGE_ID.test(id);
}
