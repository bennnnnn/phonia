@AGENTS.md

# Adding to the phone app

One home per job. The repo-root `CLAUDE.md` (Mobile map, Seams) and `docs/ARCHITECTURE.md`
(mobile feature shape) are the map; this is the recipe.

## A feature

`features/<name>/` owns its product behavior. Use only the folders it needs:

| Folder | Holds | Example |
| --- | --- | --- |
| `api.ts` | the API slice (below) | `features/memory/api.ts` |
| `screens/` | one default-export screen per route | `features/memory/screens/MemoryScreen.tsx` |
| `components/` | views only this feature draws | `features/memory/components/MemoryComposer.tsx` |
| `hooks/` | state and effects a screen uses; the screen stays thin | `features/memory/hooks/useMemoryDocuments.ts` |
| `model/` | pure logic, caches and module stores; no React | `features/memory/model/memoryDocuments.ts` |
| `types.ts` | shapes the feature's API returns | `features/memory/types.ts` |

Another feature imports what it needs from these files; it never copies them. Shared,
product-free code goes to `lib/<domain>/`; a reusable control goes to `ui/` (catalog:
`ui/README.md`), never into a feature.

## A screen

1. The screen is `features/<name>/screens/<Name>Screen.tsx` (default export).
2. The route is a one-line adapter: `app/<route>.tsx` is
   `export { default } from "@/features/<name>/screens/<Name>Screen";`.
3. Its header and transition: a root route gets a `Stack.Screen` in `app/_layout.tsx`;
   a Settings page is one row in `SETTINGS_PAGES` (`app/settings/_layout.tsx`).
   Nested stacks share `nestedStackScreenOptions` and `useStackHeaderOptions`
   (`lib/stackHeader.ts`).
4. Screen state that must not outlive the account or the visit uses
   `useAccountViewOwner()` (`key` remounts it, `isCurrent()` guards late callbacks).

## An API call

1. Add a method to the feature slice, on the shared client:
   `request<T>(path, token, init)` from `lib/api/client.ts` (the bearer token, token refresh,
   timeouts, the account fence and 401/403 handling live there, and a request that finds no
   API, no answer or a 502/503/504, asks the connection check to look
   (`lib/api/connectionFailures.ts`); `requestRaw` and `requestSse` for bodies and streams).
   No raw `fetch` to our API anywhere else.
2. A new slice is spread into `api` in the `lib/api.ts` barrel. Screens and hooks call
   `api.<method>`; tests mock `@/lib/api`.
3. Response types go in the feature's `types.ts`, or `lib/api/types.ts` when several
   features read them.

## A cached list or page

Data that is shown again before it is fetched again (drawer chats, memory pages, gallery)
is a port onto `SessionResourceCache` (`lib/cache/sessionResource.ts`): it fences each
account, sends one request per key, replays edits made during a read, and tells "empty"
from "failed". A cheap stale-while-revalidate value uses `StaleResourceCache`. A list kept on
disk for a cold start (the drawer's chats, `lib/cache/chatListFile.ts`) goes back in with
`seed`: shown at once, never fresh, so the screen still reads it; its file names the account
that wrote it. An open chat's settled thread is kept by `features/chat/model/messageCache.ts`
(memory at once, the file when idle) so the next open paints it, and a reopen within the stale
window skips the read. Send works on that painted page; a turn sent before the chat's page lands
waits for it (`whenOpenedPageSettled`, `features/chat/model/openedPage.ts`), so the page never
holds the new turn. A screen showing a list reads it again once the API answers after an outage
with `useReconnectRefresh(refresh, { readAt })` (`hooks/useReconnectRefresh.ts`): its usual read, a
random 0–10 s later, only while it has focus, and none when `readAt` (its cache's fetch time) says a
read landed since the connection was lost.

A module-level value that components read with `useSyncExternalStore` is a
`createValueStore` (or `createListenerSet` for plain notifications) from `lib/listenerSet.ts`.

A new account starts with nothing of the last one. A module-level store, or a file
written to the cache directory, that can hold an account's data is cleared in
`lib/signOutCleanup.ts` (cache files take a prefix in `lib/accountFiles.ts`) or is
scoped to the session; `lib/__tests__/accountState.test.ts` lists every store and fails
on one it doesn't know.

## A setting

1. The row comes from `features/account/components/settingsUi.tsx`: `SettingsGroup`,
   `SettingsSwitchRow`, `SettingsMenuRow` (a choice opens the `SelectMenu` popover, never an
   inline list), `SettingsLinkRow`, `SettingsValueRow`. `useSettingsAction()` runs one
   action at a time with confirm and error reporting.
2. A server-side preference is a `User` field written with `updateUser` from `useAuth()`.
3. A device-only preference is a file pref (`lib/filePrefs.ts`), never SecureStore.

## Copy, dialogs and feedback

- Every string is an i18n key: add it to `lib/i18n/en.json` and the other eight locales
  (the parity test fails otherwise).
- Ask before acting with `confirmDialog`, inform with `alertDialog` (`ui/overlay/dialogs`);
  report a passing success or failure with `useActionFeedbackOptional()` or
  `reportRecoverableError`. Never `Alert`, `Modal` or `Switch` from `react-native`.

## Checks

`pnpm typecheck`, `pnpm lint`, `npx jest <paths>`, and from the repo root
`python3 scripts/check_file_sizes.py mobile` (a file over 500 lines needs a recorded reason
and may only shrink).
