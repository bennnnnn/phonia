import { shouldBlockSend } from "@/features/chat/model/sendLogic";

/** "offline" and "streaming" tell the user why; "blocked" is silent. */
type SendGuardVerdict = "send" | "blocked" | "offline" | "streaming";

/** Whether a tap on Send may start a turn. */
export function canSend(input: {
  sendInFlight: boolean;
  /** Nothing of the routed chat is on screen yet; a painted cached page is enough to send on. */
  chatLoading: boolean;
  chatId: string | null;
  routeChatId?: string;
  isOffline: boolean;
  streaming: boolean;
  text: string;
  hasAttachment: boolean;
  token: string | null;
  creating: boolean;
  /** A picked file is still being prepared; sending now would leave it behind. */
  attachPicking: boolean;
}): SendGuardVerdict {
  // A send still preparing, or a routed chat with nothing on screen yet.
  if (
    input.sendInFlight || input.chatLoading ||
    (input.routeChatId != null && input.routeChatId !== input.chatId)
  ) return "blocked";
  if (input.isOffline) return "offline";
  if (input.streaming && (input.text || input.hasAttachment)) return "streaming";
  return shouldBlockSend(input) ? "blocked" : "send";
}
