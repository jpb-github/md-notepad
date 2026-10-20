// Rendered editor bundle: schema, node views and a minimal page API.
// Task 9 adds the QWebChannel bridge and replaces `events` with bridge signals.
/* global QWebChannel, qt */
import "prosemirror-view/style/prosemirror.css";
import "./editor.css";
import { NodeSelection, Selection, EditorState } from "prosemirror-state";
import { EditorView } from "prosemirror-view";
import { schema } from "./schema.js";
import { createNodeViews, displayPlugins } from "./nodeviews.js";

// Calls meant for Python, recorded until Task 9 sends them over the bridge.
const events = [];
const callbacks = { editProtected: (index) => events.push(["editProtected", index]) };
const plugins = displayPlugins(callbacks);

function createState(json) {
  if (!json) return EditorState.create({ schema, plugins });
  const doc = schema.nodeFromJSON(json);
  doc.check(); // throws on content the schema does not allow
  return EditorState.create({ schema, plugins, doc });
}

const view = new EditorView(document.getElementById("editor"), {
  state: createState(null),
  nodeViews: createNodeViews(),
});

window.mdEditor = {
  schema,
  view,
  events,
  setDocument: (json) => view.updateState(createState(json)),
  getDocument: () => view.state.doc.toJSON(),
  // Caret at the start of top-level block `index`; atoms (protected blocks, rules) are selected.
  focusBlock: (index) => {
    const { doc } = view.state;
    if (!Number.isInteger(index) || index < 0 || index >= doc.childCount) return;
    let pos = 0;
    for (let i = 0; i < index; i++) pos += doc.child(i).nodeSize;
    const block = doc.child(index);
    const selection = block.isLeaf ? NodeSelection.create(doc, pos) : Selection.near(doc.resolve(pos + 1));
    view.dispatch(view.state.tr.setSelection(selection).scrollIntoView());
    view.focus();
  },
};

// qwebchannel.js is loaded by its own <script> before this bundle.
new QWebChannel(qt.webChannelTransport, (channel) => {
  channel.objects.bridge.ready();
});
