import { useEffect, useRef } from "react";
import * as Notifications from "expo-notifications";
import { usePathname, useRouter } from "expo-router";

import { useAuthOptional } from "@/contexts/AuthContext";
import {
  configurePushNotificationHandler,
  handlePushNotificationResponse,
} from "@/features/notifications/model/pushNotifications";
import {
  cancelTodoReminder,
} from "@/features/todos/model/todoReminders";
import {
  isRemotePushTrigger,
  todoIdFromNotificationData,
} from "@/features/todos/model/todoReminderPush";

/** Handles push notification taps and configures foreground display. */
export function PushNotificationBootstrap() {
  const router = useRouter();
  const pathname = usePathname();
  const auth = useAuthOptional();
  const authLoading = auth?.loading ?? true;
  const coldStartHandledRef = useRef(false);
  // Read the current route without re-attaching listeners on every nav.
  const pathnameRef = useRef(pathname);
  pathnameRef.current = pathname;

  useEffect(() => {
    configurePushNotificationHandler();
  }, []);

  useEffect(() => {
    let active = true;

    const navigate = (data: Record<string, unknown> | undefined) => {
      if (!active) return;
      void handlePushNotificationResponse(
        router as Parameters<typeof handlePushNotificationResponse>[0],
        data as never,
        pathnameRef.current,
      ).catch(() => {
        if (active) console.warn("[notifications] Could not open notification");
      });
    };

    // Cold-start tap: wait until auth has settled (token restored or known
    // logged-out) so the target route doesn't mount before the session it
    // needs — and only ever consume the launch response once.
    if (!authLoading && !coldStartHandledRef.current) {
      coldStartHandledRef.current = true;
      void Notifications.getLastNotificationResponseAsync().then((response) => {
        if (response) {
          navigate(response.notification.request.content.data as Record<string, unknown>);
        }
      }).catch(() => {
        if (active) console.warn("[notifications] Could not restore startup notification");
      });
    }

    const responseSub = Notifications.addNotificationResponseReceivedListener((response) => {
      navigate(response.notification.request.content.data as Record<string, unknown>);
    });
    const receivedSub = Notifications.addNotificationReceivedListener((notification) => {
      if (!active) return;
      if (!isRemotePushTrigger(notification.request.trigger)) return;
      const todoId = todoIdFromNotificationData(
        notification.request.content.data as Record<string, unknown>,
      );
      if (todoId) void cancelTodoReminder(todoId).catch(() => {
        if (active) console.warn("[notifications] Could not cancel duplicate reminder");
      });
    });
    return () => {
      active = false;
      responseSub.remove();
      receivedSub.remove();
    };
  }, [router, authLoading]);

  return null;
}
