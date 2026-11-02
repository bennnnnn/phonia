import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useTranslation } from "react-i18next";

import { useAuthToken } from "@/contexts/AuthContext";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { getSessionGeneration } from "@/lib/auth";
import { api, type AttachmentListItem } from "@/lib/api";
import { resolveAttachmentUri } from "@/features/attachments/model/attachmentUri";
import { removeCachedGalleryItem } from "@/features/attachments/model/galleryListCache";
import { emitAppEvent } from "@/lib/appEvents";
import { shareChatAttachment } from "@/features/attachments/model/downloadChatAttachment";
import {
  galleryFileName,
  galleryImageItems,
  galleryNeighborImageId,
  isReadableTextContentType,
  libraryOpenChatHref,
} from "@/features/attachments/model/gallery";
import { isPdfContentType } from "@/lib/messageAttachments";
import {
  getGalleryLayout,
  peekGalleryLayout,
  setGalleryLayout as persistGalleryLayout,
  type GalleryLayout,
} from "@/features/attachments/model/galleryLayout";
import { notifyDestructive, tap } from "@/lib/haptics";
import { queueComposerAttachment } from "@/features/attachments/model/pendingComposerAttachment";
import { pendingFromLibraryItem } from "@/features/attachments/model/pendingFromLibraryItem";
import { reportRecoverableError } from "@/lib/reportRecoverableError";
import { libraryActionMessage } from "@/features/attachments/model/attachmentErrors";
import { confirmDialog } from "@/ui/overlay/dialogs";

export function useGalleryLibrary(
  items: AttachmentListItem[],
  removeItem: (id: string) => void,
) {
  const { t } = useTranslation();
  const router = useRouter();
  const token = useAuthToken();
  const session = getSessionGeneration();
  const params = useLocalSearchParams<{ composerThread?: string | string[] }>();
  const targetThread = Array.isArray(params.composerThread) ? params.composerThread[0] : params.composerThread;
  const feedback = useActionFeedbackOptional();
  const [layout, setLayoutState] = useState<GalleryLayout>(peekGalleryLayout);
  const [viewerId, setViewerId] = useState<string | null>(null);
  const [fileItem, setFileItem] = useState<AttachmentListItem | null>(null);
  const [actionItem, setActionItem] = useState<AttachmentListItem | null>(null);
  const [actionPoint, setActionPoint] = useState<{ x: number; y: number } | null>(null);
  /** The item being shared or attached; its tile shows a spinner meanwhile. */
  const [busyItemId, setBusyItemId] = useState<string | null>(null);
  const sharingRef = useRef(false);
  const attachingRef = useRef(false);
  const deletingRef = useRef(new Set<string>());
  const itemsRef = useRef(items);
  itemsRef.current = items;
  const layoutEditedRef = useRef(false);
  const viewRef = useRef({ focused: true, version: 0 });
  useFocusEffect(useCallback(() => {
    viewRef.current.focused = true;
    return () => { viewRef.current.focused = false; viewRef.current.version++; };
  }, []));
  const isCurrent = useCallback((version: number) =>
    viewRef.current.focused && viewRef.current.version === version && session === getSessionGeneration(), [session]);
  useLayoutEffect(() => {
    setActionItem(null);
    setViewerId(null);
    setFileItem(null);
    setBusyItemId(null);
  }, [session]);

  useEffect(() => {
    let cancelled = false;
    void getGalleryLayout().then((saved) => {
      if (!cancelled && !layoutEditedRef.current) setLayoutState(saved);
    });
    return () => { cancelled = true; };
  }, []);

  const viewerItem = viewerId ? items.find((item) => item.id === viewerId) ?? null : null;

  const setLayout = useCallback((next: GalleryLayout) => {
    layoutEditedRef.current = true;
    setLayoutState(next);
    void persistGalleryLayout(next);
  }, []);

  const toggleLayout = useCallback(() => {
    tap();
    setLayout(layout === "grid" ? "column" : "grid");
  }, [layout, setLayout]);

  const shareFile = useCallback(
    async (item: AttachmentListItem) => {
      const version = viewRef.current.version;
      if (!token || !isCurrent(version)) return;
      // One share at a time; its tile already shows a spinner.
      if (sharingRef.current) return;
      const uri = resolveAttachmentUri({
        attachmentId: item.id,
        path: item.download_url,
      });
      if (!uri) {
        reportRecoverableError(feedback, t("common.share_failed"));
        return;
      }
      sharingRef.current = true;
      setBusyItemId(item.id);
      try {
        await shareChatAttachment({
          uri,
          token,
          fileName: galleryFileName(item.content_type, item.original_filename, item.source),
          contentType: item.content_type,
        });
        if (isCurrent(version)) setActionItem((current) => current?.id === item.id ? null : current);
      } catch (shareError) {
        if (!isCurrent(version)) return;
        reportRecoverableError(feedback, libraryActionMessage(shareError, "common.share_failed", t));
      } finally {
        sharingRef.current = false;
        setBusyItemId((current) => (current === item.id ? null : current));
      }
    },
    [t, token, feedback, isCurrent],
  );

  const openChat = useCallback(
    (item: AttachmentListItem) => {
      const href = libraryOpenChatHref(item);
      if (!href) return;
      router.push(href);
    },
    [router],
  );

  const attachToComposer = useCallback(
    async (item: AttachmentListItem) => {
      const version = viewRef.current.version;
      if (!token || !isCurrent(version) || attachingRef.current) return;
      attachingRef.current = true;
      setBusyItemId(item.id);
      try {
        const pending = await pendingFromLibraryItem(item, token);
        if (!isCurrent(version)) return;
        queueComposerAttachment(pending, targetThread);
        setActionItem(null);
        setViewerId(null);
        setFileItem(null);
        if (router.canGoBack()) router.back();
        else router.replace("/");
      } catch (attachError) {
        if (!isCurrent(version)) return;
        reportRecoverableError(feedback, libraryActionMessage(attachError, "chat.attach_failed", t));
      } finally {
        attachingRef.current = false;
        setBusyItemId((current) => (current === item.id ? null : current));
      }
    },
    [feedback, router, t, token, isCurrent, targetThread],
  );

  const deleteItem = useCallback(
    async (item: AttachmentListItem) => {
      const version = viewRef.current.version;
      if (!token || !isCurrent(version) || deletingRef.current.has(item.id)) return;
      deletingRef.current.add(item.id);
      try {
        await api.deleteAttachment(token, item.id);
        if (session !== getSessionGeneration()) return;
        notifyDestructive();
        removeCachedGalleryItem(item.id);
        emitAppEvent("attachmentDeleted", { attachmentId: item.id, chatId: item.chat_id ?? null });
        if (!isCurrent(version)) return;
        // The viewer stays open on the next photo (or the one before); it
        // closes only when the deleted photo was the last one.
        const neighbor = galleryNeighborImageId(galleryImageItems(itemsRef.current), item.id);
        removeItem(item.id);
        setViewerId((current) => (current === item.id ? neighbor : current));
        setFileItem((current) => (current?.id === item.id ? null : current));
        setActionItem((current) => (current?.id === item.id ? null : current));
      } catch (deleteError) {
        if (!isCurrent(version)) return;
        reportRecoverableError(feedback, libraryActionMessage(deleteError, "gallery.delete_failed", t));
      } finally {
        deletingRef.current.delete(item.id);
      }
    },
    [token, removeItem, feedback, t, isCurrent, session],
  );

  const confirmDelete = useCallback(
    (item: AttachmentListItem) => {
      void confirmDialog({
        title: t("gallery.delete_confirm_title"),
        message: t("gallery.delete_confirm_body"),
        cancelLabel: t("common.cancel"),
        confirmLabel: t("common.delete"),
        destructive: true,
      }).then((ok) => {
        if (ok) void deleteItem(item);
      });
    },
    [t, deleteItem],
  );

  const openActions = useCallback(
    (item: AttachmentListItem, point?: { x: number; y: number }) => {
      tap();
      setActionPoint(point ?? null);
      setActionItem(item);
    },
    [],
  );

  const openImage = useCallback((item: AttachmentListItem) => {
    tap();
    setFileItem(null);
    setViewerId(item.id);
  }, []);

  const openFile = useCallback(
    (item: AttachmentListItem) => {
      tap();
      setViewerId(null);
      if (isPdfContentType(item.content_type) || isReadableTextContentType(item.content_type)) {
        setFileItem(item);
        return;
      }
      return shareFile(item);
    },
    [shareFile],
  );

  return useMemo(
    () => ({
      layout,
      toggleLayout,
      viewerItem,
      setViewerId,
      fileItem,
      setFileItem,
      actionItem,
      actionPoint,
      setActionItem,
      busyItemId,
      shareFile,
      openChat,
      attachToComposer,
      confirmDelete,
      openActions,
      openImage,
      openFile,
    }),
    [
      layout,
      toggleLayout,
      viewerItem,
      fileItem,
      actionItem,
      actionPoint,
      busyItemId,
      shareFile,
      openChat,
      attachToComposer,
      confirmDelete,
      openActions,
      openImage,
      openFile,
    ],
  );
}
