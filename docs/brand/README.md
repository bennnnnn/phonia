# Recall logo

A speech bubble with an R cut from Source Sans 3 Bold (the app's UI face), in the brand indigo `#4F56E5` (`primary` in `apps/mobile/lib/theme.ts`).

| File | What | Use |
| --- | --- | --- |
| `recall-mark.svg` | Indigo bubble, white R, transparent ground | Documents, the web, anywhere on a light ground |
| `recall-app-icon.svg` | White bubble with an indigo R on a full indigo square | The app icon (iOS rounds the corners itself) |
| `recall-mark-mono.svg` | One ink (white), the R cut out | Single-color uses: Android notification and themed icons |

The R is an outline (a path), so the files need no font.

## The app's image files

All under `apps/mobile/assets/images/`, exported from these drawings:

| File | Size | Made from |
| --- | --- | --- |
| `icon.png` | 1024, no transparency | `recall-app-icon.svg`. Also the login-screen logo and the share-sheet image |
| `android-icon-foreground.png` | 512, transparent | The white bubble at 66% scale, inside Android's safe zone |
| `android-icon-background.png` | 512 | Solid `#4F56E5` (also `android.adaptiveIcon.backgroundColor` in `app.json`) |
| `android-icon-monochrome.png` | 512, transparent | `recall-mark-mono.svg` at 66% scale, for Android 13 themed icons |
| `notification-icon.png` | 96, transparent | `recall-mark-mono.svg`. Android draws notification icons as a white silhouette |
| `splash-icon.png` | 1024, transparent corners | The app icon as a rounded tile; it reads on the white and the dark splash grounds |
| `favicon.png` | 48 | The rounded tile, for the web build |

Keep the mark at least 16px tall, and keep clear space of a quarter of its width around it. Do not recolor the bubble except to white on indigo or to the single ink of the mono file.
