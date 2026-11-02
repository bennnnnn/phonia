/**
 * Changes one feature makes that another feature's cache follows. The feature that
 * owns a cache subscribes; the feature that made the change only announces it, so
 * no feature edits another's storage (code-health audit ARCH-10).
 */
import type { User } from "@/lib/api/types";

type AppEvents = {
  /** Chats deleted: the gallery drops their photos and files. */
  chatsDeleted: { chatIds: readonly string[] };
  /** A photo or file deleted from the gallery: the chat that showed it reads again. */
  attachmentDeleted: { attachmentId: string; chatId: string | null };
  /** A picture saved into a chat (image generation): the gallery reads again. */
  attachmentAdded: { chatId: string };
  /** Memory changed outside the memory screens (a settings card in a chat). */
  memoryChanged: Record<string, never>;
  /** The server saved a change this device made to these profile fields. */
  userUpdated: { fields: readonly (keyof User)[] };
};

type AppEventName = keyof AppEvents;
type Listener<K extends AppEventName> = (event: AppEvents[K]) => void;

const listeners: { [K in AppEventName]: Set<Listener<K>> } = {
  chatsDeleted: new Set(),
  attachmentDeleted: new Set(),
  attachmentAdded: new Set(),
  memoryChanged: new Set(),
  userUpdated: new Set(),
};

/** Follow an event; the returned function stops following it. */
export function onAppEvent<K extends AppEventName>(name: K, listener: Listener<K>): () => void {
  const following = listeners[name] as Set<Listener<K>>;
  following.add(listener);
  return () => {
    following.delete(listener);
  };
}

/** Tell every follower. One follower that throws does not stop the others. */
export function emitAppEvent<K extends AppEventName>(name: K, event: AppEvents[K]): void {
  for (const listener of [...(listeners[name] as Set<Listener<K>>)]) {
    try {
      listener(event);
    } catch (error) {
      if (typeof __DEV__ !== "undefined" && __DEV__) console.warn(`[appEvents] ${name} follower failed`, error);
    }
  }
}
