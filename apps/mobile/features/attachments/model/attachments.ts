import { Linking } from "react-native";
import * as DocumentPicker from "expo-document-picker";
import * as ImagePicker from "expo-image-picker";
import { File } from "expo-file-system";

import { api } from "@/lib/api";
import { uploadAttachmentBytes } from "@/features/attachments/api";
import { AttachmentError, presignFailure } from "@/features/attachments/model/attachmentErrors";
import { DOCUMENT_MIME_TYPES, MAX_ATTACHMENT_BYTES } from "@/features/attachments/model/attachmentLimits";
import { localFileSize, preparePickedAsset, type PickedAsset } from "@/features/attachments/model/attachmentPrep";
import { discardLocalCopy } from "@/features/attachments/model/localAttachmentFile";
import { getSessionGeneration, requireTokenSession, SessionChangedError } from "@/lib/auth";
import { cameraPermissionNeedsSettings } from "@/lib/cameraPermission";
import i18n from "@/lib/i18n";
import { confirmDialog } from "@/ui/overlay/dialogs";

export type AttachmentKind = "image" | "file";

export type PendingAttachment = {
  localUri: string;
  contentType: string;
  fileName: string;
  kind: AttachmentKind;
  /** Dimensions of a square-crop library selection before profile preparation. */
  imageSize?: { width: number; height: number };
  /** Library item already on the server — skip re-upload; the API clones if linked. */
  existingAttachmentId?: string;
  /** The composer uploaded `existingAttachmentId` and no message links it, so dropping the draft cancels it. */
  uploadedForDraft?: boolean;
};

let nativePickerActive = false;
let nativePickerGeneration = 0;

/** Hung native pickers must not leave picking dead for the rest of the session. */
const NATIVE_PICKER_WATCHDOG_MS = 60_000;

export class NativePickerBusyError extends Error {
  constructor() {
    super("NATIVE_PICKER_BUSY");
    this.name = "NativePickerBusyError";
  }
}

export class NativePickerTimeoutError extends Error {
  constructor() {
    super("NATIVE_PICKER_TIMEOUT");
    this.name = "NativePickerTimeoutError";
  }
}

export class PhotoLibraryPermissionError extends Error {
  readonly needsSettings: boolean;
  constructor(needsSettings: boolean) {
    super("PHOTO_LIBRARY_PERMISSION");
    this.name = "PhotoLibraryPermissionError";
    this.needsSettings = needsSettings;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isPickerConflictError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return message.toLowerCase().includes("document picking in progress");
}

async function withNativePicker<T>(run: () => Promise<T>): Promise<T | null> {
  if (nativePickerActive) throw new NativePickerBusyError();
  nativePickerActive = true;
  const generation = ++nativePickerGeneration;
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    let lastError: unknown;
    const runWithRetries = async () => {
      for (let attempt = 0; attempt < 4; attempt += 1) {
        try {
          return await run();
        } catch (error) {
          lastError = error;
          if (!isPickerConflictError(error) || attempt === 3) throw error;
          await sleep(300 * (attempt + 1));
        }
      }
      throw lastError;
    };
    return await Promise.race([
      runWithRetries(),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => {
          if (generation === nativePickerGeneration) {
            reject(new NativePickerTimeoutError());
          }
        }, NATIVE_PICKER_WATCHDOG_MS);
      }),
    ]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
    if (generation === nativePickerGeneration) {
      nativePickerActive = false;
    }
  }
}

function guessKind(contentType: string): AttachmentKind {
  return contentType.startsWith("image/") ? "image" : "file";
}

function normalizeContentType(mimeType: string | null | undefined, uri: string): string {
  const base = (mimeType ?? "").split(";")[0].trim().toLowerCase();
  if (base && base !== "application/octet-stream") {
    if (base === "image/jpg" || base === "image/pjpeg") return "image/jpeg";
    return base;
  }
  const ext = uri.split("?")[0]?.split(".").pop()?.toLowerCase();
  const documentTypes: Record<string, string> = {
    pdf: "application/pdf", txt: "text/plain", md: "text/markdown",
    csv: "text/csv", json: "application/json",
    docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  };
  if (ext && documentTypes[ext]) return documentTypes[ext];
  if (ext === "heic") return "image/heic";
  if (ext === "heif") return "image/heif";
  if (ext === "png") return "image/png";
  if (ext === "webp") return "image/webp";
  if (ext === "gif") return "image/gif";
  if (ext === "jpg" || ext === "jpeg") return "image/jpeg";
  return "application/octet-stream";
}

async function assetToPending(asset: PickedAsset): Promise<PendingAttachment> {
  return preparePickedAsset({
    ...asset,
    contentType: normalizeContentType(asset.contentType, asset.fileName || asset.uri),
  });
}

/**
 * A draft attachment nobody will send: remove its temporary copy and, with the
 * session's token, the upload made for it. A Library pick keeps its row.
 */
export function discardDraftAttachment(token: string | null, attachment: PendingAttachment | null): void {
  if (!attachment) return;
  discardLocalCopy(attachment.localUri);
  if (token && attachment.uploadedForDraft && attachment.existingAttachmentId) {
    void api.cancelAttachment(token, attachment.existingAttachmentId).catch(() => {
      // Best-effort: the server reaps unlinked uploads.
    });
  }
}

function defaultAttachmentPrompt(pending: PendingAttachment): string {
  return pending.kind === "image" ? "" : "Summarize this file.";
}

/** Text sent to the API for a message that may include an attachment. */
export function messageTextForSend(
  text: string,
  attached: PendingAttachment | null | undefined,
): string {
  const trimmed = text.trim();
  if (trimmed) return trimmed;
  if (!attached) return "";
  return defaultAttachmentPrompt(attached);
}

async function ensureSquareCropPermission(): Promise<void> {
  let permission = await ImagePicker.getMediaLibraryPermissionsAsync();
  if (!permission.granted && !cameraPermissionNeedsSettings(permission)) {
    permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
  }
  if (!permission.granted) {
    throw new PhotoLibraryPermissionError(cameraPermissionNeedsSettings(permission));
  }
}

export async function pickFromPhotoLibrary(
  options: { squareCrop?: boolean } = {},
): Promise<PendingAttachment | null> {
  return withNativePicker(async () => {
    // The system Photos picker does not need library permission. Checking
    // first turned a denied status into Settings instead of the picker.
    // The square crop editor still uses the legacy picker, which does need it.
    if (options.squareCrop) await ensureSquareCropPermission();

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.85,
      allowsEditing: options.squareCrop ?? false,
      ...(options.squareCrop ? { aspect: [1, 1] as [number, number] } : {}),
    });

    if (result.canceled || !result.assets[0]) return null;

    const asset = result.assets[0];
    const fileName = asset.fileName ?? `photo-${Date.now()}.jpg`;
    if (options.squareCrop) {
      // Profile preparation validates size and performs the final JPEG conversion.
      // Avoid a separate full-size HEIC conversion before those checks.
      const contentType = normalizeContentType(asset.mimeType, fileName || asset.uri);
      return {
        localUri: asset.uri,
        contentType,
        fileName,
        kind: guessKind(contentType),
        imageSize: { width: asset.width, height: asset.height },
      };
    }
    return await assetToPending({ uri: asset.uri, contentType: asset.mimeType ?? "", fileName });
  });
}

function isMissingCameraPermission(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return message.toLowerCase().includes("missing camera");
}

async function offerCameraSettings(): Promise<void> {
  const open = await confirmDialog({
    title: i18n.t("chat.camera_permission"),
    message: i18n.t("chat.camera_settings_body"),
    cancelLabel: i18n.t("chat.camera_settings_not_now"),
    confirmLabel: i18n.t("chat.location_open_settings"),
  });
  if (open) void Linking.openSettings();
}

function launchCamera() {
  return ImagePicker.launchCameraAsync({
    mediaTypes: ["images"],
    quality: 0.85,
    allowsEditing: false,
  });
}

export async function pickFromCamera(): Promise<PendingAttachment | null> {
  return withNativePicker(async () => {
    // Launch immediately when access is already granted. iOS rejects the
    // launch otherwise, and only then do we show the system permission prompt.
    let result: ImagePicker.ImagePickerResult;
    try {
      result = await launchCamera();
    } catch (error) {
      if (!isMissingCameraPermission(error)) throw error;
      const permission = await ImagePicker.requestCameraPermissionsAsync();
      if (!permission.granted) {
        if (cameraPermissionNeedsSettings(permission)) {
          // Only Settings can turn it back on: ask before leaving the app.
          await offerCameraSettings();
          return null;
        }
        throw new AttachmentError("camera_permission");
      }
      result = await launchCamera();
    }

    if (result.canceled || !result.assets[0]) return null;

    const asset = result.assets[0];
    return await assetToPending({
      uri: asset.uri,
      contentType: asset.mimeType ?? "",
      fileName: asset.fileName ?? `camera-${Date.now()}.jpg`,
    });
  });
}

async function pickDocumentWithTypes(types: string[]): Promise<PendingAttachment | null> {
  return withNativePicker(async () => {
    const result = await DocumentPicker.getDocumentAsync({
      type: types,
      copyToCacheDirectory: true,
      multiple: false,
    });

    if (result.canceled || !result.assets[0]) return null;

    const asset = result.assets[0];
    return await assetToPending({
      uri: asset.uri,
      contentType: asset.mimeType ?? "application/octet-stream",
      fileName: asset.name ?? `file-${Date.now()}`,
    });
  });
}

/** Native Files picker for scanner images; it never requests photo-library access. */
export async function pickImageDocument(): Promise<PendingAttachment | null> {
  return pickDocumentWithTypes(["image/*"]);
}

export async function pickDocument(): Promise<PendingAttachment | null> {
  return pickDocumentWithTypes(["image/*", ...DOCUMENT_MIME_TYPES]);
}

export async function uploadChatAttachment(
  token: string,
  pending: PendingAttachment,
): Promise<string> {
  requireTokenSession(token);
  const generation = getSessionGeneration();
  const requireCurrent = () => {
    if (generation !== getSessionGeneration()) throw new SessionChangedError();
  };
  if (pending.existingAttachmentId) return pending.existingAttachmentId;

  const sizeBytes = localFileSize(pending.localUri);
  // Picks are checked when chosen; a restored or Library draft is checked here, before presign.
  if (sizeBytes > MAX_ATTACHMENT_BYTES) throw new AttachmentError("too_large");
  const presign = await api.presignAttachment(token, {
    content_type: pending.contentType,
    size_bytes: sizeBytes,
    filename: pending.fileName,
  }).catch((error: unknown) => {
    throw presignFailure(error);
  });
  try {
    requireCurrent();
    const bytes = await new File(pending.localUri).arrayBuffer();
    requireCurrent();
    if (bytes.byteLength !== sizeBytes) throw new AttachmentError("changed");
    await uploadAttachmentBytes(token, presign, pending.contentType, bytes);
    requireCurrent();

    if (!presign.api_upload) {
      await api.confirmAttachment(token, presign.attachment_id);
      requireCurrent();
    }

    try {
      const { invalidateGalleryCache } = await import("@/features/attachments/model/galleryListCache");
      invalidateGalleryCache();
    } catch {
      /* best-effort */
    }

    requireCurrent();
    return presign.attachment_id;
  } catch (error) {
    try {
      await api.cancelAttachment(token, presign.attachment_id);
    } catch {
      /* best-effort refund */
    }
    throw error;
  }
}
