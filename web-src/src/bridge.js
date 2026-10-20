// QWebChannel glue: the calls the Rendered editor makes on Python's Bridge object
// (mdviewer/richview.py). Python calls the editor through window.mdEditor (editor.js).
/* global QWebChannel, qt */

// Every call the page makes on the Python Bridge, in spec section 6.2 order. The Python
// Bridge needs a slot for each one; send() refuses any other name.
export const CALLS = [
  "ready",
  "changed",
  "selectionState",
  "requestLinkDialog",
  "requestImageDialog",
  "openLink",
  "hoverLink",
  "editProtected",
  "caretBlock"
];

let bridge = null;

export function send(name, ...args) {
  if (!CALLS.includes(name)) throw new Error(`bridge: unknown call ${name}`);
  if (bridge) bridge[name](...args);
}

// Connects to the channel's "bridge" object, then tells Python the page is ready.
// Calls made before that are dropped: Python ignores the page until ready().
export function connectBridge() {
  if (typeof qt === "undefined") return; // page opened outside Qt, e.g. in a browser
  // qwebchannel.js is loaded by its own <script> before the bundle.
  new QWebChannel(qt.webChannelTransport, (channel) => {
    bridge = channel.objects.bridge;
    send("ready");
  });
}
