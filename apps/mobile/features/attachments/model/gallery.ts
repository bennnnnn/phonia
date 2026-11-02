import type { AttachmentListItem } from "@/features/attachments/types";

export const GALLERY_SEARCH_DEBOUNCE_MS = 300;
export const GALLERY_PAGE_SIZE = 30;
export const GALLERY_GRID_COLUMNS = 3;
export const COLUMN_THUMB_SIZE = 64;

export type GalleryFilter = "all" | "uploaded" | "files";

type GalleryListParams = {
  category?: "images" | "files";
};

export function isGalleryImage(contentType: string): boolean {
  return contentType.startsWith("image/");
}

export function galleryPressAction(contentType: string): "view-image" | "open-file" {
  return isGalleryImage(contentType) ? "view-image" : "open-file";
}

export function isReadableTextContentType(contentType: string): boolean {
  const base = contentType.split(";")[0].trim().toLowerCase();
  return base.startsWith("text/") || base === "application/json";
}

export function galleryImageItems(items: AttachmentListItem[]): AttachmentListItem[] {
  return items.filter((item) => isGalleryImage(item.content_type));
}

export function galleryImageIndex(images: AttachmentListItem[], id: string): number {
  const index = images.findIndex((item) => item.id === id);
  return index >= 0 ? index : 0;
}

export type GalleryItemAction = "use" | "open_chat" | "share" | "delete";

/** What the long-press menu offers for an item, in its order (screen readers get the same list). */
export function galleryItemActions(item: Pick<AttachmentListItem, "chat_id">): GalleryItemAction[] {
  return item.chat_id ? ["use", "open_chat", "share", "delete"] : ["use", "share", "delete"];
}

export function libraryOpenChatHref(
  item: Pick<AttachmentListItem, "chat_id" | "message_id">,
): {
  pathname: "/";
  params: { chatId: string; returnTo: "gallery"; highlightMessage?: string };
} | null {
  if (!item.chat_id) return null;
  // Push a second instance of the main chat route; returnTo=gallery flips the
  // header from hamburger to Back so the user returns to Library.
  return {
    pathname: "/",
    params: {
      chatId: item.chat_id,
      returnTo: "gallery",
      ...(item.message_id ? { highlightMessage: item.message_id } : {}),
    },
  };
}

export function galleryEmptyKey(
  filter: GalleryFilter,
  query = "",
):
  | "gallery.empty"
  | "gallery.empty_files"
  | "gallery.empty_search"
  | "gallery.empty_uploaded" {
  if (query.trim()) return "gallery.empty_search";
  if (filter === "files") return "gallery.empty_files";
  if (filter === "uploaded") return "gallery.empty_uploaded";
  return "gallery.empty";
}

export function galleryListParams(filter: GalleryFilter): GalleryListParams {
  if (filter === "files") return { category: "files" };
  if (filter === "uploaded") return { category: "images" };
  // All: the API lists only uploads (lookup photos stay on the chat).
  return {};
}

export function galleryListCacheKey(filter: GalleryFilter, query: string): string {
  return `${filter}:${query.trim()}`;
}

/** File extensions for the types Library holds; anything else uses its MIME subtype. */
const MIME_EXTENSIONS: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/jpg": "jpg",
  "image/png": "png",
  "image/gif": "gif",
  "image/webp": "webp",
  "image/heic": "heic",
  "image/heif": "heif",
  "image/svg+xml": "svg",
  "application/pdf": "pdf",
  "application/json": "json",
  "text/plain": "txt",
  "text/markdown": "md",
  "text/csv": "csv",
  "text/html": "html",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
  "application/msword": "doc",
  "application/vnd.ms-excel": "xls",
};

/** The extension for a content type (`image/jpeg` → `jpg`), or null when it has none. */
export function extensionForContentType(contentType: string): string | null {
  const base = contentType.split(";")[0]?.trim().toLowerCase() ?? "";
  const known = MIME_EXTENSIONS[base];
  if (known) return known;
  const subtype = base.split("/")[1]?.split("+")[0]?.trim();
  if (!subtype) return null;
  const ext = subtype.includes(".") ? subtype.slice(subtype.lastIndexOf(".") + 1) : subtype;
  return /^[a-z0-9]{1,12}$/.test(ext) ? ext : null;
}

/** The MIME type for a file name's extension (`cat.JPG` → `image/jpeg`), or null when unknown. */
export function contentTypeForFileName(fileName: string): string | null {
  const ext = fileName.match(/\.([A-Za-z0-9]{1,12})$/)?.[1]?.toLowerCase();
  if (!ext) return null;
  if (ext === "jpeg") return "image/jpeg";
  return Object.entries(MIME_EXTENSIONS).find(([, value]) => value === ext)?.[0] ?? null;
}

/**
 * The name a Library item gets when it is shared, saved or attached: its file
 * name, ending with the extension of its type.
 */
export function galleryFileName(contentType: string, originalFilename?: string | null): string {
  const ext = extensionForContentType(contentType);
  const withExt = (stem: string) => (ext ? `${stem}.${ext}` : stem);
  const named = originalFilename?.trim().replace(/\\/g, "/").split("/").pop()?.trim();
  if (named) {
    if (!ext || /\.[A-Za-z0-9]{1,8}$/.test(named)) return named;
    return withExt(named);
  }
  return withExt("attachment");
}

export function galleryThumbSize(listWidth: number, columns: number, gap: number): number {
  if (listWidth <= 0 || columns <= 0) return 1;
  return Math.max(1, Math.floor((listWidth - gap * (columns - 1)) / columns));
}

/**
 * Grid layout with one gap everywhere: each tile sits in a cell padded by
 * half the gap, and the list is inset by the gutter less that half, so the
 * space between columns, between rows and at both edges comes out the same.
 */
export function galleryGridLayout(
  screenWidth: number,
  gutter: number,
  gap: number,
  columns: number = GALLERY_GRID_COLUMNS,
): { thumbSize: number; cellPadding: number; listPadding: number } {
  return {
    thumbSize: galleryThumbSize(screenWidth - gutter * 2, columns, gap),
    cellPadding: gap / 2,
    listPadding: Math.max(0, gutter - gap / 2),
  };
}

/** The image to show after `id` is deleted from the viewer: the next one, else the one before. */
export function galleryNeighborImageId(
  images: Pick<AttachmentListItem, "id">[],
  id: string,
): string | null {
  const index = images.findIndex((item) => item.id === id);
  if (index < 0) return null;
  return images[index + 1]?.id ?? images[index - 1]?.id ?? null;
}

export function mergeGalleryItems(
  current: AttachmentListItem[],
  incoming: AttachmentListItem[],
  reset: boolean,
): AttachmentListItem[] {
  if (reset) return incoming;
  const seen = new Set(current.map((item) => item.id));
  return [...current, ...incoming.filter((item) => !seen.has(item.id))];
}
