# Rich fences (`apps/mobile/components/rich`)

A reply's fenced block (```` ```quiz ````, ```` ```graph ````, ```` ```simulation ````, …) is drawn by
one block component here. Which tags are fences, and how each one behaves everywhere else in the
app, is declared once in `lib/fenceRegistry.ts`. Read its header before adding a fence: the set is
frozen unless the thing the user sees is truly new.

## Adding a fence

1. **One row in `FENCES`** (`lib/fenceRegistry.ts`). `FenceId` is read off the table. The row
   decides, for every path at once:
   - `langs`: every tag that resolves to it.
   - `structured` / `neverCodeBlock`: whether it reaches the rich renderer, and whether it may
     ever fall back to a syntax-highlighted code card.
   - `owner`: who may write it (`model`, `server`, `legacy`).
   - `body`: what the still-open streaming tail shows. A `data` body (JSON, SMILES, numbered
     lines) is a quiet placeholder until the fence closes; a `prose` body streams as reply text;
     `latex` typesets as it streams.
   - `fallback`: how the crash fallback (`FallbackMarkdown`) degrades it when not plain code.
   - `plainText`: what Copy and Read aloud make of it (`drop`, or spoken as `chart` /
     `diagram`); omitted, the body is the text.
   - `mathDiagram`, `liftOutOfLists`: maths-only rules (no Copy on a code-card fallback; lifted
     out of list items before markdown-it reads it).
2. **One block component**, `components/rich/<Name>Block.tsx`, taking `{ content }`. Parse and
   validate the body in a pure, unit-tested reader under `lib/<domain>/`, never in the component;
   a body that does not parse never shows as raw JSON. A block that refuses its body says so with
   `useFenceRefused(id, content, refused, shape)`: Sentry gets the fence id and a reason code
   (`lib/fenceReports.ts`), rate-limited, never the body. A crash while it draws is reported by
   `FenceErrorBoundary`, tagged the same way. A block that pulls in a
   WebView, Skia or a large library is exported lazily from `LazyHeavyRich.tsx` with
   `lazyContentBlock(() => import(...), <placeholder height>)`.
3. **One case in `renderRichFenceById`** (`RichFence.tsx`). The switch is exhaustive over
   `FenceId`, so TypeScript fails until the new id has its case.
4. **Tests.** `lib/__tests__/fenceRegistry.test.ts` lists every id on purpose ("does not add
   fence types without an explicit contract change", the render-slot table): add the new id
   there, plus the reader's unit tests and a render test for the block.

Nothing else lists fences: dispatch (`lib/fenceDispatch.ts`), the open streaming tail, the code
card, copy, read aloud and the crash fallback all read the row. Only a fence whose copy and
spoken text are built from its body (a quiz, an array, an answer) adds that reader to
`lib/markdown/plain.ts`. A server-owned fence also needs
its writer and validation on the API side (see `docs/math.md`, `docs/physics.md`,
`docs/chemistry.md`).

## Conventions

- Theme colors, type roles and spacing come from `lib/theme.ts`, `lib/type.ts` and `lib/space.ts`;
  controls come from the `ui/` kit (`ui/README.md`).
- A picture is one accessible image: `accessibilityRole="image"` and a label that says what it
  shows (`DiagramFrame` does this for the physics diagrams).
- The phone draws what the server verified and walks sampled paths; it never solves or
  re-derives (CLAUDE.md rule 7).
