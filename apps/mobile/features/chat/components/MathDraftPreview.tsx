import { createContext, memo, useContext, useMemo, useRef, type ReactElement } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { DraftRadical } from "@/features/chat/components/DraftRadical";
import { MathComposerCaret } from "@/features/chat/components/MathComposerCaret";
import { MathText } from "@/components/rich/MathText";
import { splitInlineMath } from "@/lib/markdown/preprocess";
import {
  caretAfterExpression,
  caretBeforeExpression,
  findDraftNodes,
  shiftDraftNodes,
  type DraftNode,
} from "@/lib/math/draftSlots";
import { DRAFT_TEXT_SIZE, draftShowsMathPreview, scriptSize, spokenDraft, splitBeforeOperator, textRuns } from "@/lib/math/draftText";
import { healDroppedCommandSlash } from "@/lib/math/healMathSource";
import { innermostSlot, type LatexGroup } from "@/lib/math/keyboardSymbols";
import { latexNeedsTallLine, MATH_TALL_LINE_HEIGHT } from "@/lib/math/text";
import { MATH_FONT, mathFace } from "@/lib/fonts";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";

export const MATH_DRAFT_PREVIEW_HEIGHT = 48;


type ScriptNode = Extract<DraftNode, { kind: "script" }>;

/** ∑, ∏, and lim carry their scripts above and below. A definite integral is drawn separately. */
const LIMIT_BASE = /\\(?:sum|prod|lim)\s*$/;

const INTEGRAL_BASE = /\\int\s*$/;
const INTEGRAL_SIGN_SIZE = 32;
const INTEGRAL_SIGN_LINE = 36;

/** The formula's text size here; a script's provider makes it smaller. */
const DraftTextSize = createContext(DRAFT_TEXT_SIZE);


function isLimitBase(input: string, node: DraftNode): boolean {
  return node.kind === "text" && LIMIT_BASE.test(input.slice(node.start, node.end).replace(/\$/g, ""));
}

function isIntegralBase(input: string, node: DraftNode): boolean {
  return node.kind === "text" && INTEGRAL_BASE.test(input.slice(node.start, node.end).replace(/\$/g, ""));
}

/** A superscript or subscript belongs on the previous symbol, not as the next item in the row. */
function clusterDraftNodes(nodes: DraftNode[]): { node: DraftNode; scripts: ScriptNode[] }[] {
  const groups: { node: DraftNode; scripts: ScriptNode[] }[] = [];
  for (let i = 0; i < nodes.length; i += 1) {
    const node = nodes[i]!;
    if (node.kind === "script") {
      const prev = groups[groups.length - 1];
      if (prev) prev.scripts.push(node);
      else groups.push({ node, scripts: [] });
      continue;
    }
    const scripts: ScriptNode[] = [];
    while (nodes[i + 1]?.kind === "script") {
      scripts.push(nodes[i + 1] as ScriptNode);
      i += 1;
    }
    groups.push({ node, scripts });
  }
  return groups;
}

/** The composer's text field reads the draft; its caret targets are for sight. */
const READER_SKIPS = { accessibilityElementsHidden: true, importantForAccessibility: "no-hide-descendants" } as const;

type Props = {
  input: string;
  caret?: number;
  onMoveCaret?: (pos: number) => void;
  /** Composer only. Sent bubbles must not show an insert caret. */
  showCaret?: boolean;
  /**
   * A sent bubble sizes to its math. The composer's fixed row height left
   * empty space under one-line math such as `[4,4]`.
   */
  sent?: boolean;
};

export const MathDraftPreview = memo(function MathDraftPreview({
  input,
  caret = 0,
  onMoveCaret,
  showCaret = true,
  sent = false,
}: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  // When the input looks like math but has no `$` delimiters (e.g. "√9" or
  // "x^2 = 4"), wrap it so findDraftNodes/splitInlineMath treat it as math.
  const healed = useMemo(() => {
    const wrapped = input.includes("$") ? input : `$${input}$`;
    return healDroppedCommandSlash(wrapped, caret, caret);
  }, [input, caret]);
  const mathInput = healed.text;
  const viewCaret = healed.start;
  const nodes = useMemo(() => findDraftNodes(mathInput), [mathInput]);
  const parts = useMemo(() => splitInlineMath(mathInput), [mathInput]);
  const before = caretBeforeExpression(mathInput);
  const after = caretAfterExpression(mathInput);
  const tall = parts.some((p) => p.type === "math" && latexNeedsTallLine(p.value));
  if (!draftShowsMathPreview(input)) return null;
  const liveCaret = showCaret && viewCaret >= 0;
  const showBeforeCaret = liveCaret && viewCaret <= before && viewCaret < after;
  const showAfterCaret = liveCaret && viewCaret >= after;

  const pieces = clusterDraftNodes(nodes);
  const pieceCaret = liveCaret ? viewCaret : -1;
  return (
    <View
      style={[s.wrap, s.row, sent ? s.sent : tall && { minHeight: MATH_TALL_LINE_HEIGHT }]}
      testID="math-draft-preview"
      {...(sent ? { accessible: true, accessibilityRole: "text", accessibilityLabel: spokenDraft(mathInput) } : READER_SKIPS)}
    >
      {/* A sent bubble has no caret: its targets wrapped to an empty second line. */}
      {sent ? null : (
        <Pressable
          testID="math-slot-before"
          onPress={() => onMoveCaret?.(before)}
          style={s.edge}
          accessible={false}
        >
          {showBeforeCaret ? <MathComposerCaret testID="math-slot-before-caret" /> : null}
        </Pressable>
      )}
      {pieces.map((piece) => (
        <DraftAtom
          key={`${piece.node.kind}-${piece.node.start}`}
          piece={piece}
          input={mathInput}
          caret={pieceCaret}
          before={before}
          after={after}
          onMoveCaret={onMoveCaret}
        />
      ))}
      {sent ? null : (
        <Pressable
          testID="math-slot-after"
          onPress={() => onMoveCaret?.(after)}
          style={s.edge}
          accessible={false}
        >
          {showAfterCaret ? <MathComposerCaret testID="math-slot-after-caret" /> : null}
        </Pressable>
      )}
    </View>
  );
});

function DraftAtom({
  piece,
  input,
  caret,
  before,
  after,
  onMoveCaret,
}: {
  piece: { node: DraftNode; scripts: ScriptNode[] };
  input: string;
  caret: number;
  before: number;
  after: number;
  onMoveCaret?: (pos: number) => void;
}) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const limits = piece.scripts.length > 0 && isLimitBase(input, piece.node);
  const integral = piece.scripts.length > 0 && isIntegralBase(input, piece.node);
  const sup = piece.scripts.filter((node) => node.mark === "^");
  const sub = piece.scripts.filter((node) => node.mark === "_");
  const kit = { input, caret, before, after, onMoveCaret };
  // An operator's limits sit on the operator alone: the text before it stays text.
  const split = (integral || limits) && piece.node.kind === "text" ? splitBeforeOperator(input, piece.node) : null;
  const lead = split?.lead ? <DraftPiece node={split.lead} {...kit} /> : null;
  const base = <DraftPiece node={split?.operator ?? piece.node} {...kit} />;
  if (integral) {
    return (
      <>
        {lead}
        <View style={s.integral} testID="math-integral">
          <Text style={s.integralSign} testID="math-integral-sign">
            ∫
          </Text>
          <View style={s.integralLimits} testID="math-integral-limits">
            <ScriptStack
              scripts={sup}
              input={input}
              caret={caret}
              before={before}
              after={after}
              onMoveCaret={onMoveCaret}
              place="over"
            />
            <ScriptStack
              scripts={sub}
              input={input}
              caret={caret}
              before={before}
              after={after}
              onMoveCaret={onMoveCaret}
              place="over"
            />
          </View>
        </View>
      </>
    );
  }
  if (!limits) {
    return (
      <View style={s.atom}>
        {base}
        {piece.scripts.length > 0 ? (
          <ScriptStack
            scripts={piece.scripts}
            input={input}
            caret={caret}
            before={before}
            after={after}
            onMoveCaret={onMoveCaret}
          />
        ) : null}
      </View>
    );
  }
  return (
    <>
      {lead}
      <View style={s.limitAtom}>
        <ScriptStack
          scripts={sup}
          input={input}
          caret={caret}
          before={before}
          after={after}
          onMoveCaret={onMoveCaret}
          place="over"
        />
        {base}
        <ScriptStack
          scripts={sub}
          input={input}
          caret={caret}
          before={before}
          after={after}
          onMoveCaret={onMoveCaret}
          place="over"
        />
      </View>
    </>
  );
}

function ScriptStack({
  scripts,
  input,
  caret,
  before,
  after,
  onMoveCaret,
  place = "side",
}: {
  scripts: ScriptNode[];
  input: string;
  caret: number;
  before: number;
  after: number;
  onMoveCaret?: (pos: number) => void;
  place?: "side" | "over";
}) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  if (scripts.length === 0) return null;
  const sup = scripts.filter((node) => node.mark === "^");
  const sub = scripts.filter((node) => node.mark === "_");
  const lift = place === "side" && sup.length > 0 && sub.length === 0;
  const drop = place === "side" && sub.length > 0 && sup.length === 0;
  return (
    <View
      testID="math-script-stack"
      style={[place === "side" ? s.scriptStack : s.scriptOver, lift && s.scriptLift, drop && s.scriptDrop]}
    >
      {[...sup, ...sub].map((node) => (
        <DraftPiece
          key={`${node.mark}-${node.start}`}
          node={node}
          input={input}
          caret={caret}
          before={before}
          after={after}
          onMoveCaret={onMoveCaret}
        />
      ))}
    </View>
  );
}

type PieceProps = {
  input: string;
  caret: number;
  before: number;
  after: number;
  onMoveCaret?: (pos: number) => void;
};

/** What a piece draws with: the draft and caret, the styles, and its slots' shared props. */
type PieceKit = PieceProps & {
  s: ReturnType<typeof makeStyles>;
  theme: Theme;
  slot: { text: string; caret: number; before: number; after: number; onMoveCaret?: (pos: number) => void };
  /** Text size here: smaller inside a script. */
  size: number;
};

type PieceRenderer<K extends DraftNode["kind"]> = (
  node: Extract<DraftNode, { kind: K }>,
  kit: PieceKit,
) => ReactElement | null;

/** A run of plain draft text; a tap near its front puts the caret there, else at its end. */
const textPiece: PieceRenderer<"text"> = (node, { input, caret, before, after, onMoveCaret, s, theme, size }) => {
  const runs = textRuns(input, node.start, node.end);
  if (runs.length === 0) return null;
  let start = node.start;
  if (input[start] === "$") start += 1;
  let end = node.end;
  if (input[end - 1] === "$") end -= 1;
  return (
    <Pressable
      testID="math-slot-text"
      onPress={(e) => {
        const x = e.nativeEvent.locationX;
        onMoveCaret?.(x < 8 ? start : end);
      }}
      style={s.textHit}
      accessible={false}
    >
      <View style={s.slotRow}>
        {caret === start && start > before ? (
          <MathComposerCaret testID="math-slot-text-caret-start" />
        ) : null}
        {runs.map((run, i) =>
          run.math ? (
            <MathText key={i} latex={run.text} textColor={theme.text} fontSize={size} />
          ) : (
            <Text key={i} style={[s.prose, { fontSize: size }]}>
              {run.text}
            </Text>
          ),
        )}
        {caret === end && end < after ? <MathComposerCaret testID="math-slot-text-caret" /> : null}
      </View>
    </Pressable>
  );
};

const fracPiece: PieceRenderer<"frac"> = (node, { s, slot }) => (
  <View style={s.frac} testID="math-frac">
    <EditSlot {...slot} group={node.num} testID="math-slot-num" />
    <View style={s.vinculum} testID="math-vinculum" />
    <EditSlot {...slot} group={node.den} testID="math-slot-den" />
  </View>
);

const sqrtPiece: PieceRenderer<"sqrt"> = (node, { theme, slot }) => (
  <DraftRadical
    color={theme.text}
    index={
      node.index ? (
        <EditSlot {...slot} group={node.index} testID="math-slot-nroot-index" fontSize={12} compact />
      ) : null
    }
  >
    <EditSlot {...slot} group={node.body} testID="math-slot-sqrt" compact />
  </DraftRadical>
);

const scriptPiece: PieceRenderer<"script"> = (node, { s, slot, size }) => {
  const sub = node.mark === "_";
  return (
    <View style={s.inline} testID={sub ? "math-sub" : "math-sup"}>
      <View style={sub ? s.sub : s.sup}>
        <DraftTextSize.Provider value={scriptSize(size)}>
          <EditSlot {...slot} group={node.body} testID={sub ? "math-slot-sub" : "math-slot-sup"} />
        </DraftTextSize.Provider>
      </View>
    </View>
  );
};

const bracePiece: PieceRenderer<"brace"> = (node, { s, slot }) => (
  <View style={s.inline} testID="math-brace">
    <EditSlot {...slot} group={node.body} testID="math-slot-brace" />
  </View>
);

const absPiece: PieceRenderer<"abs"> = (node, { s, slot }) => (
  <View style={s.inline} testID="math-abs">
    <Text style={s.prose}>|</Text>
    <EditSlot {...slot} group={node.body} testID="math-slot-abs" />
    <Text style={s.prose}>|</Text>
  </View>
);

const binomPiece: PieceRenderer<"binom"> = (node, { s, slot }) => (
  <View style={s.inline} testID="math-binom">
    <Text style={s.prose}>C(</Text>
    <EditSlot {...slot} group={node.n} testID="math-slot-binom-n" />
    <Text style={s.prose}>,</Text>
    <EditSlot {...slot} group={node.k} testID="math-slot-binom-k" />
    <Text style={s.prose}>)</Text>
  </View>
);

const vecPiece: PieceRenderer<"vec"> = (node, { s, slot }) => (
  <View style={s.vec} testID="math-vec">
    <Text style={s.vecArrow}>→</Text>
    <EditSlot {...slot} group={node.body} testID="math-slot-vec" />
  </View>
);

/** `\sin(x)`, `[a]`, `\{1,2\}`: the opening text as typed, the slot, the close. */
const groupPiece: PieceRenderer<"group"> = (node, { input, s, slot }) => {
  const prefix = `${input.slice(node.start, node.body.open).replace(/\\/g, "")}${node.open}`;
  return (
    <View style={s.inline} testID="math-group">
      <Text style={s.prose}>{prefix}</Text>
      <EditSlot {...slot} group={node.body} testID="math-slot-group" />
      <Text style={s.prose}>{node.close}</Text>
    </View>
  );
};

/** One renderer per draft node kind. */
const DRAFT_PIECES: { [K in DraftNode["kind"]]: PieceRenderer<K> } = {
  text: textPiece,
  frac: fracPiece,
  sqrt: sqrtPiece,
  script: scriptPiece,
  brace: bracePiece,
  abs: absPiece,
  binom: binomPiece,
  vec: vecPiece,
  group: groupPiece,
};

function DraftPiece({ node, input, caret, before, after, onMoveCaret }: PieceProps & { node: DraftNode }) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const size = useContext(DraftTextSize);
  const slot = { text: input, caret, before, after, onMoveCaret };
  const render = DRAFT_PIECES[node.kind] as PieceRenderer<DraftNode["kind"]>;
  return render(node, { input, caret, before, after, onMoveCaret, s, theme, slot, size });
}

function EditSlot({
  text,
  group,
  caret,
  before,
  after,
  testID,
  onMoveCaret,
  compact = false,
  fontSize,
}: {
  text: string;
  group: LatexGroup;
  caret: number;
  before: number;
  after: number;
  testID: string;
  onMoveCaret?: (pos: number) => void;
  /** Radicand slot: the bar is this slot's top border, so the content needs a
   * tight line box or the digits hang well below it. */
  compact?: boolean;
  fontSize?: number;
}) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const size = useContext(DraftTextSize);
  const widthRef = useRef(0);
  const inner = text.slice(group.open + 1, group.close);
  const empty = inner.length === 0;
  const nested = inner ? shiftDraftNodes(findDraftNodes(inner), group.open + 1) : [];
  const structured = nested.some((node) => node.kind !== "text");
  const focus = innermostSlot(text, caret);
  const active =
    focus != null && focus.open === group.open && focus.close === group.close;
  const atStart = active && caret === group.open + 1;
  const atEnd = active && caret === group.close;
  return (
    <Pressable
      testID={testID}
      onLayout={(e) => {
        widthRef.current = e.nativeEvent.layout.width;
      }}
      onPress={(e) => {
        if (!inner) {
          onMoveCaret?.(group.close);
          return;
        }
        const width = widthRef.current;
        const atFront = width > 0 && e.nativeEvent.locationX < width / 2;
        onMoveCaret?.(atFront ? group.open + 1 : group.close);
      }}
      // A filled script hugs its text: the tap-target width read as a gap after the base.
      style={[s.slot, !empty && size < DRAFT_TEXT_SIZE && s.slotTight, empty && s.slotActive]}
      accessible={false}
    >
      <View style={s.slotRow}>
        {structured ? (
          clusterDraftNodes(nested).map((piece, i) => (
            <DraftAtom
              key={`${piece.node.kind}-${piece.node.start}-${i}`}
              piece={piece}
              input={text}
              caret={caret}
              before={before}
              after={after}
              onMoveCaret={onMoveCaret}
            />
          ))
        ) : (
          <>
            {inner && atStart ? <MathComposerCaret testID={`${testID}-caret-start`} /> : null}
            {inner ? (
              <MathText latex={inner} textColor={theme.text} compact={compact} fontSize={fontSize ?? size} />
            ) : active ? (
              <View style={s.placeholderActive}>
                <MathComposerCaret testID={`${testID}-caret`} />
              </View>
            ) : (
              <View style={s.placeholder} testID={`${testID}-placeholder`} />
            )}
            {inner && atEnd ? <MathComposerCaret testID={`${testID}-caret-end`} /> : null}
          </>
        )}
      </View>
    </Pressable>
  );
}

const makeStyles = (theme: Theme) =>
  StyleSheet.create({
    wrap: {
      alignSelf: "flex-start",
      width: "100%",
      minHeight: MATH_DRAFT_PREVIEW_HEIGHT,
      justifyContent: "center",
      paddingHorizontal: 2,
      marginBottom: 2,
    },
    sent: {
      minHeight: 0,
      marginBottom: 0,
    },
    row: {
      flexDirection: "row",
      flexWrap: "wrap",
      alignItems: "center",
      justifyContent: "flex-start",
      gap: 1,
    },
    atom: {
      flexDirection: "row",
      alignItems: "center",
    },
    limitAtom: {
      alignItems: "center",
    },
    integral: {
      flexDirection: "row",
      alignItems: "center",
    },
    integralSign: {
      ...mathFace(MATH_FONT),
      fontSize: INTEGRAL_SIGN_SIZE,
      lineHeight: INTEGRAL_SIGN_LINE,
      color: theme.text,
    },
    integralLimits: {
      height: INTEGRAL_SIGN_LINE,
      marginLeft: Space.xxs,
      justifyContent: "space-between",
    },
    // The base keeps 2pt of tap padding on its right; the script sits against
    // the letter, as `x²` does in a reply.
    scriptStack: {
      marginLeft: -2,
      alignItems: "flex-start",
    },
    scriptOver: {
      alignItems: "center",
    },
    scriptLift: { marginBottom: 6 },
    scriptDrop: { marginTop: 6 },
    inline: {
      flexDirection: "row",
      alignItems: "center",
    },
    // Slot text, function names and delimiters (| C( , )) are part of the
    // formula: the math face, not the system font beside KaTeX slots.
    prose: {
      ...mathFace(MATH_FONT),
      fontSize: 16,
      color: theme.text,
    },
    frac: {
      alignItems: "center",
      minWidth: 28,
    },
    vinculum: {
      alignSelf: "stretch",
      height: StyleSheet.hairlineWidth,
      backgroundColor: theme.text,
      marginVertical: 2,
    },
    vec: {
      alignItems: "center",
    },
    vecArrow: {
      ...mathFace(MATH_FONT),
      fontSize: 12,
      lineHeight: 12,
      color: theme.text,
      marginBottom: -2,
    },
    sup: { marginBottom: 2 },
    sub: { marginTop: 2 },
    slot: {
      minWidth: 12,
      minHeight: 16,
      alignItems: "center",
      justifyContent: "center",
      paddingHorizontal: 1,
    },
    slotTight: {
      minWidth: 0,
      paddingHorizontal: 0,
    },
    slotActive: {
      backgroundColor: theme.primaryLight,
      borderRadius: 4,
    },
    slotRow: {
      flexDirection: "row",
      alignItems: "center",
    },
    textHit: {
      paddingHorizontal: 2,
      minHeight: 22,
      justifyContent: "center",
    },
    placeholder: {
      width: 10,
      height: 14,
    },
    placeholderActive: {
      width: 10,
      height: 14,
      alignItems: "center",
      justifyContent: "center",
    },
    edge: {
      minWidth: 6,
      minHeight: 22,
      alignItems: "center",
      justifyContent: "center",
    },
  });
