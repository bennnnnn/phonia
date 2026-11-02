import {
  Children,
  ReactElement,
  ReactNode,
  cloneElement,
  createContext,
  isValidElement,
  memo,
  useContext,
  useMemo,
  useState,
} from "react";
import { StyleSheet, useWindowDimensions, View } from "react-native";

import { Theme, useTheme } from "@/lib/theme";
import { Space } from "@/lib/space";
import { FadingHorizontalScroll } from "@/components/markdown/FadingHorizontalScroll";
import { PARAGRAPH_GAP } from "@/components/markdown/markdownContentStyles";
import {
  sumWidths,
  tableColumnWidths,
  type TableColumnText,
} from "@/components/markdown/tableLayout";

type CellProps = { isLast?: boolean; columnIndex?: number };

type RowProps = { isLast?: boolean };

type TableLayout = {
  columnWidths: number[];
};

const TableLayoutContext = createContext<TableLayout>({
  columnWidths: [],
});

const TABLE_H_PAD = 32;
const FALLBACK_COL_WIDTH = 120;

export function tableViewportWidth(screenWidth: number, measuredWidth: number): number {
  const screenBound = Math.max(200, screenWidth - TABLE_H_PAD);
  return measuredWidth > 0 ? Math.min(measuredWidth, screenBound) : screenBound;
}

export function resolveFrozenRowHeight(left?: number, right?: number): number {
  return Math.max(left ?? 0, right ?? 0);
}

export function tableShouldFreezeFirstColumn(
  columns: number,
  viewportWidth: number,
  tableWidth: number,
): boolean {
  // On a phone, a frozen first column consumes almost half of the gesture
  // surface and makes the table feel stuck. Pan the whole grid there; retain
  // the useful frozen label column on tablet-sized viewports.
  return viewportWidth >= 600 && columns >= 3 && tableWidth > viewportWidth + 1;
}

function collectTableRows(children: ReactNode): ReactElement[] {
  const rows: ReactElement[] = [];
  for (const child of Children.toArray(children)) {
    if (!isValidElement(child)) continue;
    if (child.type === MarkdownTableRow) {
      rows.push(child);
      continue;
    }
    const nested = (child.props as { children?: ReactNode }).children;
    if (nested != null) {
      rows.push(...collectTableRows(nested));
    }
  }
  return rows;
}

function mapCells(children: ReactNode) {
  const cells = Children.toArray(children);
  return cells.map((child, index) => {
    if (!isValidElement<CellProps>(child)) return child;
    return cloneElement(child, { isLast: index === cells.length - 1, columnIndex: index });
  });
}

function mapRows(children: ReactNode) {
  const rows = Children.toArray(children);
  return rows.map((child, index) => {
    if (!isValidElement<RowProps>(child)) return child;
    return cloneElement(child as ReactElement<RowProps>, {
      isLast: index === rows.length - 1,
    });
  });
}

type Props = {
  nodeKey: string;
  /** What each column holds (tableColumnText), which sets its width. */
  columns: TableColumnText[];
  children: ReactNode;
};

export function MarkdownTable({ nodeKey, columns, children }: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const { width: screenWidth } = useWindowDimensions();
  const [viewportW, setViewportW] = useState(0);
  // Some message parents report the intrinsic table width during their first
  // layout pass. Never let that measurement exceed the physical chat canvas,
  // or `scrollable` becomes false while the last columns are clipped.
  const layoutW = tableViewportWidth(screenWidth, viewportW);
  // `columns` is read again on every parse; the cells redraw only when a width changes.
  const widthsKey = tableColumnWidths(columns, layoutW).join(",");
  const layout = useMemo(() => ({ columnWidths: widthsKey.split(",").map(Number) }), [widthsKey]);
  const { columnWidths } = layout;
  const tableWidth = sumWidths(columnWidths);

  const freezeFirst = tableShouldFreezeFirstColumn(columnWidths.length, layoutW, tableWidth);
  const rows = freezeFirst ? collectTableRows(children) : [];

  return (
    <TableLayoutContext.Provider value={layout}>
      <View
        testID="markdown-table"
        style={[s.scrollWrap, { maxWidth: layoutW }]}
        onLayout={(e) => {
          const w = Math.round(e.nativeEvent.layout.width);
          if (w > 0 && Math.abs(w - viewportW) > 1) setViewportW(w);
        }}
      >
        {freezeFirst ? (
          <FrozenFirstColumnTable
            rows={rows}
            firstWidth={columnWidths[0] ?? FALLBACK_COL_WIDTH}
            restWidth={tableWidth - (columnWidths[0] ?? 0)}
            viewportWidth={layoutW}
            theme={theme}
            styles={s}
          />
        ) : (
          // A wide table's cut-off column needs a cue that the row scrolls.
          <FadingHorizontalScroll
            testID="markdown-table-scroll"
            contentWidth={tableWidth}
            viewportWidth={layoutW}
            style={{ maxWidth: layoutW }}
          >
            <View key={nodeKey} style={[s.table, { width: tableWidth }]}>
              {mapRows(children)}
            </View>
          </FadingHorizontalScroll>
        )}
      </View>
    </TableLayoutContext.Provider>
  );
}

function FrozenFirstColumnTable({
  rows,
  firstWidth,
  restWidth,
  viewportWidth,
  theme,
  styles: s,
}: {
  rows: ReactElement[];
  firstWidth: number;
  restWidth: number;
  viewportWidth: number;
  theme: Theme;
  styles: ReturnType<typeof makeStyles>;
}) {
  const [leftHeights, setLeftHeights] = useState<number[]>([]);
  const [rightHeights, setRightHeights] = useState<number[]>([]);

  return (
    <View style={s.freezeRow}>
      <View
        style={[
          s.frozenCol,
          { width: firstWidth, backgroundColor: theme.contentSurface },
        ]}
      >
        {rows.map((row, index) => {
          const cells = mapCells((row.props as { children?: ReactNode }).children);
          const height = resolveFrozenRowHeight(leftHeights[index], rightHeights[index]);
          return (
            <View
              key={`frozen-${index}`}
              style={[s.row, index === rows.length - 1 && s.rowLast, height ? { minHeight: height } : null]}
              onLayout={(e) => {
                const h = Math.round(e.nativeEvent.layout.height);
                setLeftHeights((prev) => {
                  if (prev[index] === h) return prev;
                  const next = prev.slice();
                  next[index] = h;
                  return next;
                });
              }}
            >
              {cells[0]}
            </View>
          );
        })}
      </View>
      <FadingHorizontalScroll
        testID="markdown-table-scroll"
        contentWidth={restWidth}
        viewportWidth={viewportWidth - firstWidth}
        style={s.frozenRest}
      >
        <View>
          {rows.map((row, index) => {
            const cells = mapCells((row.props as { children?: ReactNode }).children);
            const height = resolveFrozenRowHeight(leftHeights[index], rightHeights[index]);
            return (
              <View
                key={`rest-${index}`}
                style={[
                  s.row,
                  index === rows.length - 1 && s.rowLast,
                  { width: restWidth },
                  height ? { minHeight: height } : null,
                ]}
                onLayout={(e) => {
                  const h = Math.round(e.nativeEvent.layout.height);
                  setRightHeights((prev) => {
                    if (prev[index] === h) return prev;
                    const next = prev.slice();
                    next[index] = h;
                    return next;
                  });
                }}
              >
                {cells.slice(1)}
              </View>
            );
          })}
        </View>
      </FadingHorizontalScroll>
    </View>
  );
}

type TableRowProps = {
  nodeKey: string;
  children: ReactNode;
  isLast?: boolean;
  /**
   * What the row is drawn from (`tableRowSource`) and the styles its cells were
   * drawn with. A row whose source, styles and place are as they were draws the
   * same: a streaming table, parsed again on every flush, redraws only the row
   * still being written. Without a source the row redraws with its parent.
   */
  source?: string | null;
  drawnWith?: object;
};

function sameRow(prev: TableRowProps, next: TableRowProps): boolean {
  return (
    next.source != null &&
    prev.source === next.source &&
    prev.drawnWith === next.drawnWith &&
    prev.nodeKey === next.nodeKey &&
    prev.isLast === next.isLast
  );
}

export const MarkdownTableRow = memo(function MarkdownTableRow({
  nodeKey,
  children,
  isLast = false,
}: TableRowProps) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  return (
    <View key={nodeKey} style={[s.row, isLast && s.rowLast]}>
      {mapCells(children)}
    </View>
  );
}, sameRow);

function TableCell({
  nodeKey,
  children,
  isLast = false,
  columnIndex = 0,
}: {
  nodeKey: string;
  children: ReactNode;
  isLast?: boolean;
  columnIndex?: number;
}) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const { columnWidths } = useContext(TableLayoutContext);
  const columnWidth = columnWidths[columnIndex] ?? FALLBACK_COL_WIDTH;

  return (
    <View
      key={nodeKey}
      style={[s.cell, !isLast && s.cellBorderRight, { width: columnWidth }]}
    >
      <View style={s.cellInner}>{children}</View>
    </View>
  );
}

export function MarkdownTableHeaderCell(
  props: CellProps & { nodeKey: string; children: ReactNode },
) {
  return <TableCell {...props} />;
}

export function MarkdownTableCell(
  props: CellProps & { nodeKey: string; children: ReactNode },
) {
  return <TableCell {...props} />;
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    scrollWrap: {
      marginTop: 0,
      marginBottom: PARAGRAPH_GAP,
      overflow: "hidden",
      alignSelf: "stretch",
      width: "100%",
      maxWidth: "100%",
      minWidth: 0,
      flexShrink: 1,
    },
    frozenRest: { flex: 1 },
    freezeRow: {
      flexDirection: "row",
      alignSelf: "stretch",
      width: "100%",
    },
    frozenCol: {
      zIndex: 1,
      borderRightWidth: StyleSheet.hairlineWidth,
      borderRightColor: theme.border,
    },
    table: {
      backgroundColor: "transparent",
      alignSelf: "stretch",
    },
    row: {
      flexDirection: "row",
      alignItems: "flex-start",
      backgroundColor: "transparent",
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: theme.border,
    },
    rowLast: {
      borderBottomWidth: 0,
    },
    cell: {
      backgroundColor: "transparent",
      minWidth: 0,
    },
    cellBorderRight: {
      borderRightWidth: StyleSheet.hairlineWidth,
      borderRightColor: theme.border,
    },
    cellInner: {
      paddingHorizontal: Space.sm,
      paddingVertical: Space.xs,
      minWidth: 0,
      flexShrink: 1,
    },
  });
}
