import type { AttachmentListItem } from "@/lib/api";
import type { AttachmentKind, PendingAttachment } from "@/features/attachments/model/attachments";
import { resolveAttachmentUri } from "@/features/attachments/model/attachmentUri";
import { ensureLocalAttachmentFile } from "@/features/attachments/model/downloadChatAttachment";
import { attachmentSessionGuard } from "@/features/attachments/model/attachmentSession";
import { galleryFileName } from "@/features/attachments/model/gallery";

/** Retain local bytes so a restored Library attachment can be uploaded again. */
export async function pendingFromLibraryItem(
  item: Pick<AttachmentListItem, "id" | "content_type" | "original_filename" | "download_url">,
  token: string | null,
): Promise<PendingAttachment> {
  const requireCurrent = attachmentSessionGuard(token);
  const fileName = galleryFileName(item.content_type, item.original_filename);
  const kind: AttachmentKind = item.content_type.startsWith("image/") ? "image" : "file";
  const remoteUri = resolveAttachmentUri({
    attachmentId: item.id,
    path: item.download_url,
  });
  if (!remoteUri) {
    throw new Error("Could not attach");
  }
  const localUri = await ensureLocalAttachmentFile({ uri: remoteUri, token, fileName });
  requireCurrent();
  return {
    localUri,
    contentType: item.content_type,
    fileName,
    kind,
    existingAttachmentId: item.id,
  };
}
