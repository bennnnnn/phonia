import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Linking } from "react-native";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import {
  NativePickerBusyError,
  NativePickerTimeoutError,
  PhotoLibraryPermissionError,
  uploadChatAttachment,
  type PendingAttachment,
} from "@/features/attachments/model/attachments";
import { getSessionGeneration } from "@/lib/auth";
import { sanitizeDisplayName } from "@/lib/profile";
import { discardProfilePhoto, pickProfilePhoto } from "@/features/account/model/profilePhoto";
import { confirmDialog } from "@/ui/overlay/dialogs";

type Owner = { session: number; userId: string | undefined; signedIn: boolean };
type Editor = {
  owner: Owner;
  revision: number;
  visible: boolean;
  name: string;
  photo: PendingAttachment | null;
  /** Save clears the current photo, so the initials show. */
  removePhoto: boolean;
  saving: boolean;
  picking: boolean;
  error: string | null;
};

function emptyEditor(owner: Owner, revision: number): Editor {
  return { owner, revision, visible: false, name: "", photo: null, removePhoto: false,
    saving: false, picking: false, error: null };
}

export function useProfileEditor() {
  const { user, token, updateUser } = useAuth();
  const { t } = useTranslation();
  const session = getSessionGeneration();
  const userId = user?.id;
  const signedIn = Boolean(token && userId);
  const owner = useMemo(() => ({ session, userId, signedIn }), [session, userId, signedIn]);
  const ownerRef = useRef(owner);
  ownerRef.current = owner;
  const mounted = useRef(true);
  const [state, setState] = useState(() => emptyEditor(owner, 0));
  const editor = useRef(state);

  const publish = useCallback((next: Editor) => {
    editor.current = next;
    setState(next);
  }, []);

  useEffect(() => {
    mounted.current = true;
    if (editor.current.owner !== owner) {
      publish(emptyEditor(owner, editor.current.revision + 1));
    }
    return () => {
      mounted.current = false;
      if (editor.current.owner === owner) {
        if (editor.current.photo) discardProfilePhoto(editor.current.photo);
        editor.current = emptyEditor(owner, editor.current.revision + 1);
      }
    };
  }, [owner, publish]);

  const canAct = useCallback(() => mounted.current && owner.signedIn &&
    ownerRef.current === owner && owner.session === getSessionGeneration(), [owner]);
  const isCurrent = useCallback((revision: number) => canAct() &&
    editor.current.owner === owner && editor.current.visible &&
    editor.current.revision === revision, [canAct, owner]);

  const dismiss = useCallback(() => {
    if (editor.current.photo) discardProfilePhoto(editor.current.photo);
    publish(emptyEditor(owner, editor.current.revision + 1));
  }, [owner, publish]);

  const open = useCallback(() => {
    if (!canAct() || editor.current.saving || editor.current.picking) return;
    if (editor.current.photo) discardProfilePhoto(editor.current.photo);
    publish({ ...emptyEditor(owner, editor.current.revision + 1),
      visible: true, name: user?.name ?? "" });
  }, [canAct, owner, publish, user?.name]);

  const close = useCallback(() => {
    const current = editor.current;
    if (!isCurrent(current.revision) || current.saving || current.picking) return;
    dismiss();
  }, [dismiss, isCurrent]);

  const setName = useCallback((name: string) => {
    const current = editor.current;
    if (!isCurrent(current.revision) || current.saving || current.picking) return;
    publish({ ...current, name, error: null });
  }, [isCurrent, publish]);

  const choosePhoto = useCallback(async () => {
    const current = editor.current;
    const { revision } = current;
    if (!isCurrent(revision) || current.saving || current.picking) return;
    publish({ ...current, picking: true, error: null });
    try {
      const photo = await pickProfilePhoto();
      if (!isCurrent(revision)) {
        if (photo) discardProfilePhoto(photo);
        return;
      }
      if (photo) {
        if (editor.current.photo) discardProfilePhoto(editor.current.photo);
        publish({ ...editor.current, photo, removePhoto: false });
      }
    } catch (error) {
      if (!isCurrent(revision)) return;
      if (error instanceof PhotoLibraryPermissionError) {
        void confirmDialog({
          title: t("settings.change_photo"),
          message: t("settings.photo_permission"),
          cancelLabel: t("settings.cancel"),
          confirmLabel: t("chat.location_open_settings"),
        }).then((ok) => {
          if (!ok) return;
          if (!isCurrent(revision)) return;
          void Linking.openSettings().catch(() => {
            if (isCurrent(revision)) {
              publish({ ...editor.current, error: t("settings.photo_permission") });
            }
          });
        });
      } else {
        const key = error instanceof NativePickerBusyError || error instanceof NativePickerTimeoutError
          ? "chat.picker_busy" : "settings.photo_update_failed";
        publish({ ...editor.current, error: t(key) });
      }
    } finally {
      if (isCurrent(revision)) publish({ ...editor.current, picking: false });
    }
  }, [isCurrent, publish, t]);

  const removePhoto = useCallback(() => {
    const current = editor.current;
    if (!isCurrent(current.revision) || current.saving || current.picking) return;
    if (current.photo) discardProfilePhoto(current.photo);
    publish({ ...current, photo: null, removePhoto: true, error: null });
  }, [isCurrent, publish]);

  const save = useCallback(async () => {
    const current = editor.current;
    const { revision, photo, removePhoto: clearPhoto } = current;
    if (!token || !isCurrent(revision) || current.saving || current.picking) return;
    const name = sanitizeDisplayName(current.name);
    if (!name) {
      publish({ ...current, error: t("settings.name_invalid") });
      return;
    }
    if (!photo && !clearPhoto && name === sanitizeDisplayName(user?.name ?? "")) {
      dismiss();
      return;
    }
    // Publish to the ref synchronously: two taps before a render still save once.
    publish({ ...current, saving: true, error: null });
    let uploadedId: string | null = null;
    const cancelUpload = () => {
      if (!uploadedId || owner.session !== getSessionGeneration()) return;
      // The server protects an active avatar if a successful PATCH lost its response.
      void api.cancelAttachment(token, uploadedId).catch(() => {
        // Upload cleanup is best-effort; keep the original save error actionable.
      });
    };
    try {
      if (photo) uploadedId = await uploadChatAttachment(token, photo);
      if (!isCurrent(revision)) {
        cancelUpload();
        return;
      }
      const avatar = uploadedId ? { avatar_url: `/attachments/${uploadedId}/file` } : clearPhoto ? { avatar_url: null } : {};
      await updateUser({ name, ...avatar });
      if (isCurrent(revision)) dismiss();
    } catch {
      cancelUpload();
      if (isCurrent(revision)) {
        publish({ ...editor.current, error: t(photo ? "settings.photo_update_failed" : "settings.proposal_failed") });
      }
    } finally {
      if (isCurrent(revision)) publish({ ...editor.current, saving: false });
    }
  }, [dismiss, isCurrent, owner.session, publish, t, token, updateUser, user?.name]);

  const current = state.owner === owner ? state : emptyEditor(owner, state.revision);
  return { visible: current.visible, name: current.name, setName, photo: current.photo,
    photoRemoved: current.removePhoto, saving: current.saving, picking: current.picking,
    error: current.error, open, close, choosePhoto, removePhoto, save };
}
