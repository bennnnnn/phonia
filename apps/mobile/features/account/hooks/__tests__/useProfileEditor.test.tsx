import React from "react";
import { Alert, Linking } from "react-native";
import { act, render } from "@testing-library/react-native";

import { useProfileEditor } from "@/features/account/hooks/useProfileEditor";
import { api } from "@/lib/api";
import {
  NativePickerBusyError,
  NativePickerTimeoutError,
  PhotoLibraryPermissionError,
  uploadChatAttachment,
  type PendingAttachment,
} from "@/features/attachments/model/attachments";
import { discardProfilePhoto, pickProfilePhoto } from "@/features/account/model/profilePhoto";

let mockSession = 1;
let mockUser = { id: "account-a", name: "Ada", avatar_url: "https://example.com/avatar.jpg" };
let mockToken = "test-token-a";
const mockUpdateUser = jest.fn();
jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mockUser, token: mockToken, updateUser: mockUpdateUser }),
}));
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockSession }));
jest.mock("@/lib/api", () => ({ api: { cancelAttachment: jest.fn() } }));
jest.mock("@/features/attachments/model/attachments", () => ({
  uploadChatAttachment: jest.fn(),
  NativePickerBusyError: class extends Error {},
  NativePickerTimeoutError: class extends Error {},
  PhotoLibraryPermissionError: class extends Error {
    needsSettings: boolean;
    constructor(needsSettings: boolean) {
      super("permission");
      this.needsSettings = needsSettings;
    }
  },
}));
jest.mock("@/features/account/model/profilePhoto", () => ({ pickProfilePhoto: jest.fn(), discardProfilePhoto: jest.fn() }));

const PHOTO: PendingAttachment = {
  localUri: "file:///profile-preview.jpg", contentType: "image/jpeg", fileName: "profile.jpg", kind: "image",
};
let editor: ReturnType<typeof useProfileEditor>;
function Probe() {
  const result = useProfileEditor();
  React.useLayoutEffect(() => { editor = result; });
  return null;
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
async function setup() {
  const view = await render(<Probe />);
  await act(async () => { editor.open(); });
  return view;
}
async function selectPhoto(photo = PHOTO) {
  jest.mocked(pickProfilePhoto).mockResolvedValueOnce(photo);
  await act(async () => { await editor.choosePhoto(); });
}

beforeEach(() => {
  jest.resetAllMocks();
  mockSession++;
  mockUser = { id: "account-a", name: "Ada", avatar_url: "https://example.com/avatar.jpg" };
  mockToken = "test-token-a";
  mockUpdateUser.mockResolvedValue(undefined);
  jest.mocked(api.cancelAttachment).mockResolvedValue(undefined);
  jest.mocked(uploadChatAttachment).mockResolvedValue("uploaded-photo");
  jest.spyOn(Alert, "alert").mockImplementation(() => {});
  jest.spyOn(Linking, "openSettings").mockResolvedValue(undefined);
});

it("opens from the saved profile and closes unchanged drafts without a request", async () => {
  await render(<Probe />);
  expect(editor.visible).toBe(false);
  await act(async () => { editor.open(); });
  expect(editor.name).toBe("Ada");
  await act(async () => { editor.setName("Unsaved"); });
  await act(async () => { editor.close(); editor.open(); });
  expect(editor.name).toBe("Ada");
  await act(async () => { await editor.save(); });
  expect(editor.visible).toBe(false);
  expect(mockUpdateUser).not.toHaveBeenCalled();
  expect(uploadChatAttachment).not.toHaveBeenCalled();
});

it.each(["   ", "x".repeat(81)])("rejects invalid names before saving", async (name) => {
  await setup();
  await act(async () => { editor.setName(name); await editor.save(); });
  expect(editor.error).toBe("settings.name_invalid");
  expect(editor.visible).toBe(true);
  expect(editor.saving).toBe(false);
  expect(mockUpdateUser).not.toHaveBeenCalled();
});

it("normalizes a name-only edit without replacing the photo", async () => {
  await setup();
  await act(async () => { editor.setName("  Ada   Lovelace  "); await editor.save(); });
  expect(mockUpdateUser).toHaveBeenCalledWith({ name: "Ada Lovelace" });
  expect(uploadChatAttachment).not.toHaveBeenCalled();
  expect(editor.visible).toBe(false);
});

it("removes the photo on Save, and a new pick undoes the removal", async () => {
  await setup();
  await act(async () => { editor.removePhoto(); });
  expect(editor.photoRemoved).toBe(true);
  await selectPhoto();
  expect(editor.photoRemoved).toBe(false);
  await act(async () => { editor.removePhoto(); });
  expect(discardProfilePhoto).toHaveBeenCalledWith(PHOTO);
  await act(async () => { await editor.save(); });
  expect(uploadChatAttachment).not.toHaveBeenCalled();
  expect(mockUpdateUser).toHaveBeenCalledWith({ name: "Ada", avatar_url: null });
  expect(editor.visible).toBe(false);
});

it("only previews selections and releases previews on replacement, cancel, and unmount", async () => {
  const view = await setup();
  const replacement = { ...PHOTO, localUri: "file:///replacement.jpg" };
  await selectPhoto();
  expect(editor.photo).toBe(PHOTO);
  expect(uploadChatAttachment).not.toHaveBeenCalled();
  await selectPhoto(replacement);
  expect(discardProfilePhoto).toHaveBeenCalledWith(PHOTO);
  await act(async () => { editor.close(); editor.open(); });
  expect(discardProfilePhoto).toHaveBeenCalledWith(replacement);
  await selectPhoto();
  await view.unmount();
  expect(discardProfilePhoto).toHaveBeenCalledTimes(3);
  expect(mockUpdateUser).not.toHaveBeenCalled();
});

it("uploads only on Save and blocks duplicate saves, cancellation, and photo selection while saving", async () => {
  const upload = deferred<string>();
  const update = deferred<void>();
  jest.mocked(uploadChatAttachment).mockReturnValue(upload.promise);
  mockUpdateUser.mockReturnValue(update.promise);
  await setup();
  await selectPhoto();
  let saving!: Promise<void>;
  await act(async () => {
    editor.setName("Ada Lovelace");
    saving = editor.save();
    await editor.save(); editor.close(); await editor.choosePhoto();
  });
  expect(editor.visible).toBe(true);
  expect(editor.saving).toBe(true);
  expect(uploadChatAttachment).toHaveBeenCalledTimes(1);
  expect(pickProfilePhoto).toHaveBeenCalledTimes(1);
  expect(mockUpdateUser).not.toHaveBeenCalled();
  await act(async () => { upload.resolve("avatar-id"); await Promise.resolve(); });
  expect(mockUpdateUser).toHaveBeenCalledWith({ name: "Ada Lovelace", avatar_url: "/attachments/avatar-id/file" });
  await act(async () => { update.resolve(undefined); await saving; });
  expect(editor.visible).toBe(false);
  expect(discardProfilePhoto).toHaveBeenCalledWith(PHOTO);
  expect(api.cancelAttachment).not.toHaveBeenCalled();
});

it("keeps the draft and cancels an uploaded attachment after profile persistence fails", async () => {
  mockUpdateUser.mockRejectedValueOnce(new Error("network"));
  await setup();
  await selectPhoto();
  await act(async () => { await editor.save(); });
  expect(api.cancelAttachment).toHaveBeenCalledWith("test-token-a", "uploaded-photo");
  expect(editor).toMatchObject({ visible: true, photo: PHOTO, saving: false, error: "settings.photo_update_failed" });
  expect(discardProfilePhoto).not.toHaveBeenCalled();
  await act(async () => { await editor.save(); });
  expect(editor.visible).toBe(false);
});

it("retains the selected photo after upload failure without issuing a profile request", async () => {
  jest.mocked(uploadChatAttachment).mockRejectedValue(new Error("upload"));
  await setup();
  await selectPhoto();
  await act(async () => { await editor.save(); });
  expect(editor).toMatchObject({ photo: PHOTO, saving: false, error: "settings.photo_update_failed" });
  expect(mockUpdateUser).not.toHaveBeenCalled();
  expect(api.cancelAttachment).not.toHaveBeenCalled();
});

it("keeps a failed name edit open with actionable feedback", async () => {
  mockUpdateUser.mockRejectedValue(new Error("offline"));
  await setup();
  await act(async () => { editor.setName("New name"); await editor.save(); });
  expect(editor).toMatchObject({ visible: true, name: "New name", saving: false, error: "settings.proposal_failed" });
});

it.each([
  [new NativePickerBusyError(), "chat.picker_busy"],
  [new NativePickerTimeoutError(), "chat.picker_busy"],
  [new Error("invalid image"), "settings.photo_update_failed"],
])("surfaces picker failures and releases the picking lock", async (error, key) => {
  jest.mocked(pickProfilePhoto).mockRejectedValue(error);
  await setup();
  await act(async () => { await editor.choosePhoto(); });
  expect(editor).toMatchObject({ picking: false, error: key, visible: true });
});

it("offers photo permission settings and ignores a retained alert action after editor closure", async () => {
  jest.mocked(pickProfilePhoto).mockRejectedValue(new PhotoLibraryPermissionError(true));
  await setup();
  await act(async () => { await editor.choosePhoto(); });
  expect(Alert.alert).toHaveBeenCalledWith("settings.change_photo", "settings.photo_permission", expect.any(Array));
  const action = jest.mocked(Alert.alert).mock.calls.at(-1)?.[2]?.[1]?.onPress;
  await act(async () => { action?.(); });
  expect(Linking.openSettings).toHaveBeenCalledTimes(1);
  await act(async () => { editor.close(); editor.open(); action?.(); });
  expect(Linking.openSettings).toHaveBeenCalledTimes(1);
});

it("locks cancellation while picking and discards a late selection after an account switch", async () => {
  const selection = deferred<PendingAttachment | null>();
  jest.mocked(pickProfilePhoto).mockReturnValue(selection.promise);
  const view = await setup();
  let picking!: Promise<void>;
  await act(async () => { picking = editor.choosePhoto(); editor.close(); await editor.save(); });
  expect(editor).toMatchObject({ visible: true, picking: true });
  mockSession++;
  mockUser = { ...mockUser, id: "account-b", name: "Grace" };
  mockToken = "test-token-b";
  await view.rerender(<Probe />);
  expect(editor.visible).toBe(false);
  await act(async () => { editor.open(); selection.resolve(PHOTO); await picking; });
  expect(editor).toMatchObject({ name: "Grace", photo: null, picking: false, error: null });
  expect(discardProfilePhoto).toHaveBeenCalledWith(PHOTO);
  expect(mockUpdateUser).not.toHaveBeenCalled();
});

it("releases a late picker result after unmount", async () => {
  const selection = deferred<PendingAttachment | null>();
  jest.mocked(pickProfilePhoto).mockReturnValue(selection.promise);
  const view = await setup();
  let picking!: Promise<void>;
  await act(async () => { picking = editor.choosePhoto(); });
  await view.unmount();
  await act(async () => { selection.resolve(PHOTO); await picking; });
  expect(discardProfilePhoto).toHaveBeenCalledWith(PHOTO);
});

it("cancels a late upload after unmount without updating the profile", async () => {
  const upload = deferred<string>();
  jest.mocked(uploadChatAttachment).mockReturnValue(upload.promise);
  const view = await setup();
  await selectPhoto();
  let saving!: Promise<void>;
  await act(async () => { saving = editor.save(); });
  await view.unmount();
  await act(async () => { upload.resolve("orphan-photo"); await saving; });
  expect(api.cancelAttachment).toHaveBeenCalledWith("test-token-a", "orphan-photo");
  expect(mockUpdateUser).not.toHaveBeenCalled();
});

it("ignores old save failures and retained callbacks after switching accounts", async () => {
  const update = deferred<void>();
  mockUpdateUser.mockReturnValue(update.promise);
  const view = await setup();
  await selectPhoto();
  let saving!: Promise<void>;
  const oldEditor = editor;
  await act(async () => { saving = editor.save(); await Promise.resolve(); });
  mockSession++;
  mockUser = { ...mockUser, id: "account-b", name: "Grace" };
  mockToken = "test-token-b";
  await view.rerender(<Probe />);
  await act(async () => {
    editor.open(); editor.setName("Grace Hopper");
    oldEditor.open(); await oldEditor.save(); await oldEditor.choosePhoto();
    update.reject(new Error("stale failure")); await saving;
  });
  expect(editor).toMatchObject({ visible: true, name: "Grace Hopper", photo: null, saving: false, error: null });
  expect(api.cancelAttachment).not.toHaveBeenCalled();
  expect(mockUpdateUser).toHaveBeenCalledTimes(1);
});
