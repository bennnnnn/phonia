# Recall UI kit (`apps/mobile/ui`)

One set of controls for the whole app, so a feature never builds its own
button, menu, picker or row. Features import each piece by its path
(`@/ui/controls/Button`); there is no barrel file. `ui/` never imports
product code (`@/features`, `@/components`, `@/contexts`, `@/hooks`,
`@/app`), which lint enforces.

## Which piece for which job

| Job | Use | Instead of |
| --- | --- | --- |
| Ask before acting (delete, sign out, disconnect) | `confirmDialog()` from `overlay/dialogs` | `Alert.alert` with buttons |
| Tell something that needs reading (permission, Expo Go) | `alertDialog()` from `overlay/dialogs` | `Alert.alert` |
| A passing success or error | the toast: `useActionFeedback()` or `reportRecoverableError` | a dialog |
| A toast over a full-screen viewer | mount an `ActionFeedbackProvider` inside the modal (`appearance="media"` on a black stage); while it is open every toast shows there | a dialog, or a toast hidden under the modal |
| Actions on a thing (⋮, long-press) | `overlay/Menu`, anchored to the button or the touch point | a bottom sheet of actions |
| Pick one of several from a row | `overlay/SelectMenu` (checked popover) | expanding options inline |
| Pick one of two to four in place | `controls/SegmentedControl` | a row of hand-made chips |
| Pick a number in a range (an amount, a rate, a term) | `controls/Slider` (label and value above the track; an optional marker for a reference value, tap to jump; screen-reader steps; math in `sliderValue.ts`) | a hand-built track and thumb |
| A form, the attach sources, sharing | `overlay/Sheet` | a raw `Modal` |
| Edit one text value (a profile field, a memory) | `overlay/FieldSheet` (title, hint, Save) | a hand-built sheet with a field |
| A full-screen viewer (photo, PDF, scanner) | `overlay/FullScreenModal` | a raw `Modal` |
| A full-screen viewer only some visits open (the chat's photo viewer, the scanner) | `overlay/lazyOverlay(() => import(...))`: its code loads on first open, then it stays mounted | a static import the chat screen evaluates at launch |
| A time | `pickers/TimePickerDialog` (Android clock: dial, AM/PM, keyboard entry) | `@react-native-community/datetimepicker` |
| A date (month grid, year list, min/max) | `pickers/DatePickerDialog` | the native picker |
| Share a chat or a summary | `share/ShareSheet` (preview card, Share / Copy / PDF) | `Share.share` straight from a menu |
| Copy text with a check mark | `share/useCopyText` (one timing, success haptic, a refused copy reported) | `Clipboard.setStringAsync` plus a timer in the component |
| Back, close, menu, ⋮ in a header | `controls/HeaderButton` (`plate`, `plain` in a `HeaderButtonGroup`, `media` over photos); `StackBackButton` in stacks | a hand-styled circle |
| A labelled action | `controls/Button` (pill; `sm` 36 / `md` 44 / `lg` 52; optional icon; `media` is the white pill over a photo, like the viewer's Share; `bubble` is the user's message-bubble tint, following their accent, for a card's one action, like a clarify card's button) | a `Pressable` styled as a button |
| An icon-only action inside content | `controls/IconButton` | a `Pressable` around `Icon` |
| Suggestions, filters, picked values, facts | `controls/Chip` (`assist`, `filter`, `input`, `tag`) | per-feature chip styles |
| Any list row | `list/ListRow` in a `list/ListGroup` (grouped) or on its own (plain; `ListSeparator appearance="plain"` draws the line between plain rows) | per-feature row styles |
| Typing text | `controls/TextField` (label, helper, red error, multiline) | a styled `TextInput` |
| Searching a list | `controls/SearchField` | |
| Icons and logos | `icons/Icon` (Lucide line icons; `IconSize` ladder) and `icons/brand` `BrandMark` | `@expo/vector-icons`, PNG icons |
| Loading, empty, error | `feedback/StateView`, `feedback/SkeletonLoader` (`SkeletonList` for rows, `SkeletonGrid` for tiles) | |
| Small counts | `feedback/CountBadge` | |

## Folders

- `controls/`: Button, IconButton, HeaderButton (+ HeaderButtonGroup), StackBackButton, Chip,
  SegmentedControl, Slider (`sliderValue.ts`), TextField, SearchField, AddFab (`addFabLayout.ts` gives a list the bottom
  padding that clears it).
- `list/`: ListRow, ListGroup, ListSeparator.
- `overlay/`: Overlay (the one floating layer), Menu, SelectMenu, Dialog + DialogHost +
  `dialogs.ts`, Sheet, SheetFormHeader, FullScreenModal, lazyOverlay.
- `pickers/`: ClockDial, TimePickerDialog, DatePickerDialog. The
  geometry and calendar rules live in `lib/datetime/clockDial.ts` and `calendarGrid.ts`.
- `share/`: ShareSheet, useCopyText.
- `icons/`: Icon, BrandMark, the icon manifest and generated glyphs, IconSize.
- `feedback/`: ActionBanner (the toast), StateView, SkeletonLoader, CountBadge, ActionShimmer.
- `hooks/`: useKeyboardHeight, useBottomLiftStyle (bottom chrome that rides a keyboard-lifted composer on the UI thread),
  useLiveAnnouncement (the iOS half of a live region: VoiceOver hears a result or error that appears).

## Tokens

Pieces draw from the tokens in `lib/`: colors in `theme.ts` (`elevated` for popups, `control`
for plates and wells, `separator`, `pressed`, `wash`), type roles and `Weight` in `type.ts`,
`space.ts`, `radius.ts`, and springs in `motion.ts`. Lint rejects raw font sizes, font
weights, spacing, radii and hex colors outside a short list of domain graphics.

## How popups float

`Overlay` is the one layer every menu, dialog and picker opens in. On iOS it is a
`FullWindowOverlay`, so it can open over a sheet or another modal; on Android it is a
transparent `Modal`, which already stacks. It stays mounted through its closing fade.
`Sheet` is a real `Modal`: keep a sheet open while the OS share menu is on top of it, since
closing the presenter takes the share menu down with it on iOS (`ShareSheet` does this for you).

## Guardrails

- `@expo/vector-icons` and `@react-native-community/datetimepicker` cannot be imported.
- `Alert` and `Modal` from `react-native` only inside `ui/overlay`; `Switch` only inside `ui/`
  (use `ListRow` with `switchValue`). Tests may still spy on `Alert`.
- With no `DialogHost` mounted (tests, isolated hooks), `confirmDialog` and `alertDialog` fall
  back to `Alert.alert` with the old arguments.
- Controls play their own haptic (`lib/haptics`): a `Menu` row, a `SegmentedControl` segment, a
  filter `Chip`, a switch `ListRow`, picker steps, `Dialog` actions, `useCopyText`'s success. The
  action behind them adds none, so one press is one haptic.

## Adding an icon

Add the name and its Lucide id to `icons/manifest.json`, then run `pnpm icons`. App-only
drawings go in `icons/custom.tsx`; logos go in `icons/brand.tsx`.
