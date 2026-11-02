import { useCallback, useMemo } from "react";

import { AttachmentImageViewer } from "@/features/attachments/components/AttachmentImageViewer";
import { AttachmentPdfViewer } from "@/features/attachments/components/AttachmentPdfViewer";
import { AttachmentTextViewer } from "@/features/attachments/components/AttachmentTextViewer";
import { GalleryItemActionsMenu } from "@/features/attachments/components/GalleryItemActionsMenu";
import { useGalleryLibrary } from "@/features/attachments/hooks/useGalleryLibrary";
import type { AttachmentListItem } from "@/lib/api";
import {
  galleryDisplayName,
  galleryFileName,
  galleryImageIndex,
  galleryImageItems,
  galleryPressAction,
  isReadableTextContentType,
} from "@/features/attachments/model/gallery";
import type { AttachmentViewerImage } from "@/features/attachments/model/imageViewer";
import { isPdfContentType } from "@/lib/messageAttachments";

type Props = {
  items: AttachmentListItem[];
  library: ReturnType<typeof useGalleryLibrary>;
  /** Loads the Library's next page when the viewer nears its last photo. */
  onLoadMore?: () => void;
};

export function GalleryMediaModals({ items, library, onLoadMore }: Props) {
  const viewerItem = library.viewerItem;
  const fileItem = library.fileItem;
  const { setViewerId } = library;
  const images = useMemo(() => galleryImageItems(items), [items]);
  const viewerImages = useMemo(
    () =>
      images.map((item): AttachmentViewerImage => ({
        attachmentId: item.id,
        path: item.download_url,
        fileName: galleryFileName(item.content_type, item.original_filename, item.source),
        label: galleryDisplayName(item),
        chatId: item.chat_id ?? null,
      })),
    [images],
  );
  const viewerIndex = viewerItem ? galleryImageIndex(images, viewerItem.id) : 0;
  const fileName = fileItem
    ? galleryFileName(fileItem.content_type, fileItem.original_filename, fileItem.source)
    : null;
  const sharingFile = fileItem != null && library.busyItemId === fileItem.id;

  const itemForId = (id?: string | null) => items.find((item) => item.id === id);
  // The viewer follows the photo on screen, so a delete or a page load acts on it.
  const onIndexChange = useCallback(
    (image: AttachmentViewerImage) => {
      if (image.attachmentId) setViewerId(image.attachmentId);
    },
    [setViewerId],
  );

  return (
    <>
      <AttachmentImageViewer
        visible={viewerItem != null && galleryPressAction(viewerItem.content_type) === "view-image"}
        onClose={() => library.setViewerId(null)}
        images={viewerImages}
        initialIndex={viewerIndex}
        onIndexChange={onIndexChange}
        onNearEnd={onLoadMore}
        onOpenChat={(image) => {
          const item = itemForId(image.attachmentId);
          library.setViewerId(null);
          if (item?.chat_id) library.openChat(item);
        }}
        onUseInChat={(image) => {
          const item = itemForId(image.attachmentId);
          if (item) void library.attachToComposer(item);
        }}
        onDelete={(image) => {
          const item = itemForId(image.attachmentId);
          if (item) library.confirmDelete(item);
        }}
      />

      <AttachmentPdfViewer
        visible={fileItem != null && isPdfContentType(fileItem.content_type)}
        onClose={() => library.setFileItem(null)}
        attachmentId={fileItem?.id}
        path={fileItem?.download_url ?? null}
        fileName={fileName ?? "document.pdf"}
        sharing={sharingFile}
        onShare={() => {
          if (fileItem) void library.shareFile(fileItem);
        }}
      />

      <AttachmentTextViewer
        visible={fileItem != null && isReadableTextContentType(fileItem.content_type)}
        onClose={() => library.setFileItem(null)}
        attachmentId={fileItem?.id}
        path={fileItem?.download_url ?? null}
        fileName={fileName ?? "file.txt"}
        sharing={sharingFile}
        onShare={() => {
          if (fileItem) void library.shareFile(fileItem);
        }}
      />

      <GalleryItemActionsMenu
        visible={library.actionItem != null}
        anchorPoint={library.actionPoint}
        canOpenChat={Boolean(library.actionItem?.chat_id)}
        onClose={() => library.setActionItem(null)}
        onUseInChat={() => {
          const item = library.actionItem;
          if (item) void library.attachToComposer(item);
        }}
        onOpenChat={() => {
          const item = library.actionItem;
          library.setActionItem(null);
          if (item) library.openChat(item);
        }}
        onShare={() => {
          const item = library.actionItem;
          if (!item) return;
          void library.shareFile(item);
        }}
        onDelete={() => {
          const item = library.actionItem;
          if (!item) return;
          library.confirmDelete(item);
        }}
      />
    </>
  );
}
