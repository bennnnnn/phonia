/**
 * Whether the server holds this device's push token: reminders then come from the server,
 * and the phone schedules none of its own. Without one (Expo Go, no notification
 * permission, no EAS project, a failed registration, push switched off) the phone
 * schedules its reminders itself, so they still fire. No native module here: the to-do
 * context reads it without loading expo-notifications.
 */

import { createValueStore } from "@/lib/listenerSet";

const registered = createValueStore(false);

export function setRemotePushRegistered(value: boolean): void {
  registered.set(value);
}

export function remotePushRegistered(): boolean {
  return registered.get();
}

export function subscribeRemotePushRegistered(listener: () => void): () => void {
  return registered.subscribe(listener);
}
