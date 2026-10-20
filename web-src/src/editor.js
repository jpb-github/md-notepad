// Minimal Phase 0 editor: proves the bundle loads under the page CSP and talks
// to Python over QWebChannel. Task 8 replaces the schema; Task 9 the API.
/* global QWebChannel, qt */
import "prosemirror-view/style/prosemirror.css";
import { Schema } from "prosemirror-model";
import { EditorState } from "prosemirror-state";
import { EditorView } from "prosemirror-view";

const schema = new Schema({
  nodes: {
    doc: { content: "paragraph+" },
    paragraph: { content: "text*", toDOM: () => ["p", 0], parseDOM: [{ tag: "p" }] },
    text: {},
  },
});

const view = new EditorView(document.getElementById("editor"), {
  state: EditorState.create({ schema }),
});

window.mdEditor = {
  getDocument: () => view.state.doc.toJSON(),
};

// qwebchannel.js is loaded by its own <script> before this bundle.
new QWebChannel(qt.webChannelTransport, (channel) => {
  channel.objects.bridge.ready();
});
