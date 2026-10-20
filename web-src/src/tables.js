// Tables in the Rendered editor: prosemirror-tables (cell selection, arrow keys), Tab
// between cells, the commands of the cell context menu, and Markdown's table shape.
import { keymap } from "prosemirror-keymap";
import { Plugin, TextSelection } from "prosemirror-state";
import {
  addColumnAfter, addColumnBefore, addRowAfter, addRowBefore, deleteColumn, deleteRow, deleteTable,
  goToNextCell, isInTable, selectedRect, selectionCell, tableEditing,
} from "prosemirror-tables";
import { schema } from "./schema.js";

const { nodes } = schema;
const ALIGNMENTS = ["left", "center", "right"];

// Tab moves to the next cell; in the last cell it adds a row and moves into it.
function nextCell(state, dispatch) {
  if (goToNextCell(1)(state, dispatch)) return true;
  if (!isInTable(state)) return false;
  if (dispatch) {
    const rowEnd = selectionCell(state).after();
    let tr = null;
    addRowAfter(state, (added) => { tr = added; });
    if (!tr) return false;
    dispatch(tr.setSelection(TextSelection.create(tr.doc, rowEnd + 2)).scrollIntoView());
  }
  return true;
}

// Aligns the columns of the selected cells, header included.
function setColumnAlign(state, dispatch, align) {
  if (!ALIGNMENTS.includes(align) || !isInTable(state)) return false;
  if (dispatch) {
    const { map, left, right, tableStart } = selectedRect(state);
    const tr = state.tr;
    for (let row = 0; row < map.height; row++) {
      for (let col = left; col < right; col++) {
        const pos = tableStart + map.map[row * map.width + col];
        tr.setNodeMarkup(pos, null, { ...state.doc.nodeAt(pos).attrs, align });
      }
    }
    dispatch(tr);
  }
  return true;
}

const tableCommand = (command) => ({
  run: (state, dispatch) => command(state, dispatch),
  can: (state) => command(state),
});

// Cell context menu commands (Python builds the menu from selectionState.can).
export const TABLE_COMMANDS = {
  addRowBefore: tableCommand(addRowBefore),
  addRowAfter: tableCommand(addRowAfter),
  addColumnBefore: tableCommand(addColumnBefore),
  addColumnAfter: tableCommand(addColumnAfter),
  deleteRow: tableCommand(deleteRow),
  deleteColumn: tableCommand(deleteColumn),
  deleteTable: tableCommand(deleteTable),
  // args: "left" | "center" | "right"
  setColumnAlign: {
    run: (state, dispatch, view, align) => setColumnAlign(state, dispatch, align),
    can: (state) => isInTable(state),
  },
};

// The cells of `table` on a grid: merged cells are split (the content stays in the
// top-left cell) and short rows are padded with empty cells.
function cellGrid(table) {
  const grid = [];
  table.forEach((row, offset, r) => {
    grid[r] = grid[r] || [];
    let c = 0;
    row.forEach((cell) => {
      while (grid[r][c]) c++;
      const colspan = cell.attrs.colspan || 1;
      const rowspan = cell.attrs.rowspan || 1;
      for (let dr = 0; dr < rowspan && r + dr < table.childCount; dr++) {
        grid[r + dr] = grid[r + dr] || [];
        for (let dc = 0; dc < colspan; dc++) grid[r + dr][c + dc] = dr || dc ? cell.type.create() : cell;
      }
      c += colspan;
    });
  });
  return grid;
}

// Puts the table at `pos` into the shape Markdown can hold: the first row is the header
// row, no merged cells, all rows as wide as the widest, every cell aligned like its
// column's header cell. Merged cells and short rows rebuild the table; otherwise only
// the cells that differ change, so the caret stays where it is.
function fixTableShape(tr, pos, table) {
  const grid = cellGrid(table);
  const width = Math.max(...grid.map((row) => row.length));
  const reshape = grid.some((row, r) => row.length !== width || table.child(r).childCount !== width)
    || table.childCount !== grid.length;
  const typeAt = (r) => (r === 0 ? nodes.table_header : nodes.table_cell);
  const alignAt = (c) => grid[0][c]?.attrs.align ?? null;
  if (reshape) {
    const rows = grid.map((row, r) => nodes.table_row.create(null, Array.from({ length: width }, (_, c) => (
      typeAt(r).create({ align: alignAt(c) }, row[c]?.content)
    ))));
    tr.replaceWith(pos, pos + table.nodeSize, nodes.table.create(table.attrs, rows));
    return;
  }
  let cellPos = pos + 1;
  table.forEach((row, offset, r) => {
    cellPos += 1;
    row.forEach((cell, cellOffset, c) => {
      if (cell.type !== typeAt(r) || cell.attrs.align !== alignAt(c)) {
        tr.setNodeMarkup(cellPos, typeAt(r), { ...cell.attrs, align: alignAt(c) });
      }
      cellPos += cell.nodeSize;
    });
    cellPos += 1;
  });
}

// Keeps every table the transaction touched in Markdown's shape (paste, drop, row and
// column commands). Grouped with the change in the undo history.
const tableShapePlugin = new Plugin({
  appendTransaction(transactions, oldState, newState) {
    if (!transactions.some((tr) => tr.docChanged)) return null;
    const start = oldState.doc.content.findDiffStart(newState.doc.content);
    if (start === null) return null;
    const end = Math.max(start, oldState.doc.content.findDiffEnd(newState.doc.content).b);
    const tr = newState.tr;
    newState.doc.nodesBetween(start, end, (node, pos) => {
      if (node.type !== nodes.table) return true;
      fixTableShape(tr, tr.mapping.map(pos), node);
      return false;
    });
    return tr.docChanged ? tr : null;
  },
});

// The shape plugin goes before tableEditing(), whose own table fixing would otherwise
// rearrange merged cells first; the keymap goes before the other keymaps, so Tab and
// Shift+Tab move between cells inside tables.
export function tablePlugins() {
  return [tableShapePlugin, tableEditing(), keymap({ Tab: nextCell, "Shift-Tab": goToNextCell(-1) })];
}
