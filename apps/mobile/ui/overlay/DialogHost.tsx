import { useCallback, useEffect, useRef, useState } from "react";

import { OVERLAY_EXIT_MS } from "./Overlay";
import { Dialog } from "./Dialog";
import { registerDialogHost, type DialogRequest } from "./dialogs";

/**
 * Shows `confirmDialog()` / `alertDialog()` requests as themed dialogs, one at a time.
 * Mount once near the app root, inside the theme and i18n providers.
 */
export function DialogHost() {
  const queue = useRef<DialogRequest[]>([]);
  const active = useRef(false);
  const answered = useRef(false);
  const [current, setCurrent] = useState<DialogRequest | null>(null);
  const [visible, setVisible] = useState(false);

  const showNext = useCallback(() => {
    const next = queue.current.shift() ?? null;
    answered.current = false;
    active.current = next != null;
    setCurrent(next);
    setVisible(next != null);
  }, []);

  useEffect(
    () =>
      registerDialogHost((request) => {
        queue.current.push(request);
        if (!active.current) showNext();
      }),
    [showNext],
  );

  if (!current) return null;

  return (
    <Dialog
      visible={visible}
      title={current.title}
      message={current.message}
      actions={current.actions.map((action) => ({
        ...action,
        onPress: () => {
          answered.current = true;
          action.onPress?.();
        },
      }))}
      onClose={() => {
        if (!answered.current) current.onDismiss();
        setVisible(false);
        // Let the exit fade finish, then show the next queued dialog.
        setTimeout(showNext, OVERLAY_EXIT_MS + 30);
      }}
    />
  );
}
