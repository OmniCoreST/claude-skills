/* uifb overlay - injected into the reviewed app by the proxy.
 *
 * Hard rule: this file borrows nothing from the page it lands in. Every node it
 * creates lives inside a shadow root, every class is `uifb-` prefixed, the host
 * is reset with `all: initial`, and there are no imports, no fonts and no
 * globals beyond one guard flag. If the app's CSS could reach in here, the
 * panel would change appearance from project to project and the reviewer would
 * never be sure whether a visual bug was theirs or ours.
 */
(function () {
  "use strict";

  if (window.__uifbLoaded) return;
  // Only the outermost app frame gets a panel. A nested iframe inside the app
  // is proxied too, and mounting there would stack a second panel on top.
  if (window.self !== window.top && window.parent !== window.top) return;
  window.__uifbLoaded = true;

  var API = "/__uifb/api";
  var Z = "2147483000";
  // Framed by the review shell, or opened on its own? The shell carries its own
  // controls and its own list, so inside it the app frame stays free of our
  // chrome; standalone, this overlay is the entire interface.
  var IN_SHELL = window.self !== window.top;

  var state = {
    mode: "idle",        // idle | pick | region
    hover: null,
    items: [],
    pinsVisible: !IN_SHELL,
    inShell: IN_SHELL,
    draft: null,
  };

  /* ------------------------------------------------------------------ shell */

  var host = document.createElement("div");
  host.id = "uifb-root";
  host.setAttribute("data-uifb", "1");
  host.style.cssText = "all:initial;position:fixed;inset:0;pointer-events:none;z-index:" + Z + ";";
  var root = host.attachShadow({ mode: "open" });

  var CSS = `
:host { all: initial; }
* { box-sizing: border-box; margin: 0; padding: 0; font-family: ui-sans-serif, system-ui,
    -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
.uifb-layer { position: fixed; inset: 0; pointer-events: none; }
.uifb-capture { pointer-events: auto; cursor: crosshair; }

.uifb-hi { position: fixed; border: 2px solid #7c5cff; background: rgba(124,92,255,.12);
    border-radius: 3px; pointer-events: none; transition: all .06s linear; }
.uifb-hi.uifb-region { transition: none; border-style: dashed; }
.uifb-tag { position: fixed; background: #7c5cff; color: #fff; font-size: 11px; font-weight: 600;
    padding: 2px 6px; border-radius: 4px 4px 0 0; white-space: nowrap; pointer-events: none;
    letter-spacing: .01em; }

.uifb-launch { position: fixed; right: 16px; bottom: 16px; pointer-events: auto; display: flex;
    gap: 6px; align-items: center; background: #12141c; border: 1px solid #2b3040;
    border-radius: 999px; padding: 6px; box-shadow: 0 8px 28px rgba(0,0,0,.45); }
.uifb-btn { pointer-events: auto; display: inline-flex; align-items: center; gap: 6px;
    background: #1b1f2b; color: #cfd6e6; border: 1px solid #2b3040; border-radius: 999px;
    font-size: 12px; font-weight: 600; padding: 7px 12px; cursor: pointer; line-height: 1;
    transition: background .12s, color .12s, border-color .12s; }
.uifb-btn:hover { background: #232838; color: #fff; }
.uifb-btn.uifb-on { background: #7c5cff; border-color: #7c5cff; color: #fff; }
.uifb-btn.uifb-ghost { background: transparent; border-color: transparent; color: #8b93a7; }
.uifb-btn.uifb-ghost:hover { color: #fff; background: #232838; }
.uifb-btn.uifb-primary { background: #7c5cff; border-color: #7c5cff; color: #fff; }
.uifb-btn.uifb-primary:hover { background: #6a49f5; }
.uifb-count { background: #2b3040; color: #cfd6e6; border-radius: 999px; font-size: 11px;
    padding: 2px 7px; font-weight: 700; }
.uifb-count.uifb-hot { background: #7c5cff; color: #fff; }

.uifb-card { position: fixed; width: 340px; max-width: calc(100vw - 24px); background: #12141c;
    border: 1px solid #2b3040; border-radius: 12px; box-shadow: 0 18px 50px rgba(0,0,0,.55);
    pointer-events: auto; overflow: hidden; }
.uifb-card header { display: flex; align-items: center; gap: 8px; padding: 10px 12px;
    border-bottom: 1px solid #232838; }
.uifb-card h2 { font-size: 12px; font-weight: 700; color: #fff; letter-spacing: .02em; flex: 1; }
.uifb-body { padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.uifb-target { font-size: 11px; color: #8b93a7; background: #0d0f16; border: 1px solid #232838;
    border-radius: 8px; padding: 8px; display: flex; flex-direction: column; gap: 4px;
    max-height: 96px; overflow: auto; }
.uifb-target code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10.5px;
    color: #a8b3ff; word-break: break-all; }
.uifb-target .uifb-src { color: #35c48c; }
textarea.uifb-input { width: 100%; min-height: 84px; resize: vertical; background: #0d0f16;
    border: 1px solid #2b3040; border-radius: 8px; color: #e6eaf5; font-size: 13px; padding: 9px;
    line-height: 1.5; outline: none; }
textarea.uifb-input:focus { border-color: #7c5cff; }
textarea.uifb-input::placeholder { color: #59617a; }
.uifb-kinds { display: flex; gap: 6px; flex-wrap: wrap; }
.uifb-chip { font-size: 11px; font-weight: 600; padding: 5px 10px; border-radius: 999px;
    border: 1px solid #2b3040; background: #0d0f16; color: #8b93a7; cursor: pointer; }
.uifb-chip.uifb-on { color: #fff; border-color: #7c5cff; background: rgba(124,92,255,.18); }
.uifb-row { display: flex; gap: 8px; align-items: center; }
.uifb-row.uifb-end { justify-content: flex-end; }
.uifb-hint { font-size: 11px; color: #59617a; flex: 1; }

.uifb-pin { position: fixed; width: 22px; height: 22px; border-radius: 999px 999px 999px 2px;
    background: #7c5cff; color: #fff; font-size: 11px; font-weight: 700; display: flex;
    align-items: center; justify-content: center; pointer-events: auto; cursor: pointer;
    box-shadow: 0 3px 10px rgba(0,0,0,.5); border: 1.5px solid #12141c; }
.uifb-pin.uifb-s-in_progress { background: #f0a63a; }
.uifb-pin.uifb-s-sent { background: #3a9df0; }
.uifb-pin.uifb-s-open { background: #7c5cff; }
.uifb-pin:hover { transform: scale(1.15); }

.uifb-toast { position: fixed; left: 50%; transform: translateX(-50%); bottom: 76px;
    background: #12141c; border: 1px solid #2b3040; color: #e6eaf5; font-size: 12px;
    padding: 9px 14px; border-radius: 999px; pointer-events: none;
    box-shadow: 0 10px 30px rgba(0,0,0,.5); }
.uifb-flash { position: fixed; border: 2px solid #35c48c; border-radius: 4px; pointer-events: none;
    background: rgba(53,196,140,.14); animation: uifb-pulse 1.4s ease-out 2; }
@keyframes uifb-pulse { 0%,100% { opacity: 1 } 50% { opacity: .25 } }
`;

  var style = document.createElement("style");
  style.textContent = CSS;
  root.appendChild(style);

  var layer = el("div", "uifb-layer");
  root.appendChild(layer);

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function mount() {
    (document.body || document.documentElement).appendChild(host);
  }
  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount, { once: true });

  /* ------------------------------------------------------------- launcher */

  var launcher = el("div", "uifb-launch");
  var pickBtn = el("button", "uifb-btn", "Mark element");
  var regionBtn = el("button", "uifb-btn", "Draw region");
  var pinBtn = el("button", "uifb-btn uifb-ghost", "Pins");
  var countBadge = el("span", "uifb-count", "0");
  launcher.append(pickBtn, regionBtn, pinBtn, countBadge);
  // Only standalone. In the shell these three buttons sit in the top bar and
  // the rail is the list of feedback, so a dock over the app would duplicate
  // both - and the reviewer is judging a design, which is hard enough without
  // our furniture in the corner of it. The buttons are still built either way:
  // mode changes arrive from the shell and toggle their state on these nodes,
  // detached, which keeps one code path for both modes.
  if (!state.inShell) layer.appendChild(launcher);

  pickBtn.onclick = function () { setMode(state.mode === "pick" ? "idle" : "pick"); };
  regionBtn.onclick = function () { setMode(state.mode === "region" ? "idle" : "region"); };
  pinBtn.onclick = function () {
    state.pinsVisible = !state.pinsVisible;
    pinBtn.classList.toggle("uifb-on", state.pinsVisible);
    renderPins();
  };
  pinBtn.classList.add("uifb-on");

  /* ------------------------------------------------------------ highlight */

  var hi = el("div", "uifb-hi");
  var tag = el("div", "uifb-tag");
  hi.style.display = tag.style.display = "none";
  layer.append(hi, tag);

  function showHighlight(rect, label, region) {
    hi.className = "uifb-hi" + (region ? " uifb-region" : "");
    hi.style.display = "block";
    hi.style.left = rect.left + "px";
    hi.style.top = rect.top + "px";
    hi.style.width = rect.width + "px";
    hi.style.height = rect.height + "px";
    if (label) {
      tag.style.display = "block";
      tag.textContent = label;
      tag.style.left = rect.left + "px";
      tag.style.top = Math.max(0, rect.top - 18) + "px";
    } else {
      tag.style.display = "none";
    }
  }
  function hideHighlight() { hi.style.display = tag.style.display = "none"; }

  /* ----------------------------------------------------------------- mode */

  // "composing" is a mode of its own, not a flavour of "pick". While the
  // composer is open the page must stop being clickable-for-selection, or the
  // reviewer's click on our own kind chips gets read as picking a new element
  // and their half-written comment is thrown away.
  function applyChrome() {
    var mode = state.mode;
    pickBtn.classList.toggle("uifb-on", mode === "pick");
    regionBtn.classList.toggle("uifb-on", mode === "region");
    layer.classList.toggle("uifb-capture", mode === "region");
    document.documentElement.style.cursor = mode === "pick" ? "crosshair" : "";
  }

  function setMode(mode) {
    if (mode !== "composing") closeComposer();
    state.mode = mode;
    applyChrome();
    if (mode === "idle" || mode === "composing") hideHighlight();
    else toast(mode === "pick" ? "Click any element - Esc to cancel"
                               : "Drag a rectangle - Esc to cancel");
    post({ type: "uifb:mode", mode: mode });
  }

  /* Did this event come out of our own panel?
   *
   * composedPath() crosses the shadow boundary, so without this check every
   * button we render looks to the page-level listeners like a normal element
   * the reviewer wants to comment on. */
  function fromUs(e) {
    var path = e.composedPath && e.composedPath();
    if (!path) return false;
    for (var i = 0; i < path.length; i++) {
      if (path[i] === host || path[i] === root) return true;
    }
    return false;
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && (state.mode !== "idle" || composer)) {
      setMode("idle");
      e.stopPropagation();
    }
    // Alt+M / Alt+R are unlikely to collide with app shortcuts and keep the
    // reviewer's hands on the keyboard while walking a page.
    if (e.altKey && (e.key === "m" || e.key === "M")) setMode(state.mode === "pick" ? "idle" : "pick");
    if (e.altKey && (e.key === "r" || e.key === "R")) setMode(state.mode === "region" ? "idle" : "region");
  }, true);

  /* --------------------------------------------------------- element pick */

  function deepTarget(e) {
    var path = e.composedPath && e.composedPath();
    if (path && path.length) {
      for (var i = 0; i < path.length; i++) {
        var n = path[i];
        if (n instanceof Element && n !== host && !n.hasAttribute("data-uifb")) return n;
      }
    }
    return e.target;
  }

  document.addEventListener("mousemove", function (e) {
    if (state.mode !== "pick" || fromUs(e)) return;
    var target = deepTarget(e);
    if (!target || target === state.hover) return;
    state.hover = target;
    var r = target.getBoundingClientRect();
    showHighlight(r, describe(target), false);
  }, true);

  document.addEventListener("click", function (e) {
    if (state.mode !== "pick" || fromUs(e)) return;
    e.preventDefault();
    e.stopPropagation();
    var target = deepTarget(e);
    if (!target) return;
    var rect = target.getBoundingClientRect();
    openComposer(buildTarget(target, rect, "element"), rect);
  }, true);

  // Some frameworks act on mousedown/mouseup before click ever fires; swallow
  // them while picking so the review click cannot mutate the app's state.
  ["mousedown", "mouseup", "pointerdown", "pointerup", "dblclick"].forEach(function (evt) {
    document.addEventListener(evt, function (e) {
      if (state.mode === "pick" && !fromUs(e)) { e.preventDefault(); e.stopPropagation(); }
    }, true);
  });

  /* ----------------------------------------------------------- region draw */

  var dragStart = null;
  layer.addEventListener("mousedown", function (e) {
    if (state.mode !== "region") return;
    dragStart = { x: e.clientX, y: e.clientY };
    e.preventDefault();
  });
  layer.addEventListener("mousemove", function (e) {
    if (!dragStart) return;
    showHighlight(rectOf(dragStart, e), null, true);
  });
  layer.addEventListener("mouseup", function (e) {
    if (!dragStart) return;
    var rect = rectOf(dragStart, e);
    dragStart = null;
    if (rect.width < 8 || rect.height < 8) { hideHighlight(); return; }
    var center = elementUnder(rect.left + rect.width / 2, rect.top + rect.height / 2);
    openComposer(buildTarget(center, rect, "region"), rect);
  });

  /* While a region is being drawn our own capture layer sits on top of the
   * page, so a plain elementFromPoint answers "the feedback panel" - which is
   * never what the reviewer just drew a box around. Walk the stack instead and
   * take the first thing that is not ours. */
  function elementUnder(x, y) {
    var stack = document.elementsFromPoint
      ? document.elementsFromPoint(x, y)
      : [document.elementFromPoint(x, y)];
    for (var i = 0; i < stack.length; i++) {
      var n = stack[i];
      if (!n || n === host) continue;
      if (n.hasAttribute && n.hasAttribute("data-uifb")) continue;
      return n;
    }
    return null;
  }

  function rectOf(a, e) {
    return {
      left: Math.min(a.x, e.clientX), top: Math.min(a.y, e.clientY),
      width: Math.abs(e.clientX - a.x), height: Math.abs(e.clientY - a.y),
    };
  }

  /* ------------------------------------------------------------- composer */

  var composer = null;

  function openComposer(target, rect) {
    closeComposer();
    state.draft = { target: target, kind: "change" };

    composer = el("div", "uifb-card");
    var head = document.createElement("header");
    head.append(el("h2", null, target.mode === "region" ? "Feedback on region"
                                                        : "Feedback on element"));
    var close = el("button", "uifb-btn uifb-ghost", "Esc");
    close.onclick = function () { setMode("idle"); };
    head.appendChild(close);

    var body = el("div", "uifb-body");

    var summary = el("div", "uifb-target");
    var sel = el("div");
    sel.append(el("code", null, target.selector || "(region)"));
    summary.appendChild(sel);
    if (target.text) summary.appendChild(el("div", null, '"' + target.text + '"'));
    if (target.source_hint) summary.appendChild(el("div", "uifb-src", "source: " + target.source_hint));
    summary.appendChild(el("div", null, target.route + "  -  " + target.viewport.w + "x" + target.viewport.h));

    var input = el("textarea", "uifb-input");
    input.placeholder = "What should change here, and why?";

    var kinds = el("div", "uifb-kinds");
    ["bug", "change", "idea", "question"].forEach(function (k) {
      var chip = el("button", "uifb-chip" + (k === "change" ? " uifb-on" : ""), k);
      chip.onclick = function () {
        state.draft.kind = k;
        Array.prototype.forEach.call(kinds.children, function (c) {
          c.classList.toggle("uifb-on", c === chip);
        });
      };
      kinds.appendChild(chip);
    });

    var actions = el("div", "uifb-row uifb-end");
    var hint = el("div", "uifb-hint", "Ctrl+Enter to save");
    var save = el("button", "uifb-btn uifb-primary", "Add to list");
    save.onclick = function () { submit(input.value.trim()); };
    actions.append(hint, save);

    body.append(summary, input, kinds, actions);
    composer.append(head, body);
    layer.appendChild(composer);
    place(composer, rect);

    // Stop selecting, but keep the marked area outlined so the reviewer can
    // see what they are describing while they type.
    state.mode = "composing";
    applyChrome();
    showHighlight(rect, null, target.mode === "region");
    input.focus();

    input.addEventListener("keydown", function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit(input.value.trim());
      e.stopPropagation();
    });

    function submit(text) {
      if (!text) { input.focus(); return; }
      createItem(text, state.draft.kind, target, rect);
      setMode("idle");
    }
  }

  function closeComposer() {
    if (composer && composer.parentNode) composer.parentNode.removeChild(composer);
    composer = null;
    state.draft = null;
  }

  function place(node, rect) {
    var w = 340, margin = 12;
    var left = Math.min(Math.max(margin, rect.left), window.innerWidth - w - margin);
    var top = rect.top + rect.height + 10;
    if (top + 300 > window.innerHeight) top = Math.max(margin, rect.top - 300);
    node.style.left = left + "px";
    node.style.top = top + "px";
  }

  /* ----------------------------------------------------------- target data */

  function buildTarget(node, rect, mode) {
    var target = {
      mode: mode,
      route: location.pathname + location.search + location.hash,
      url: location.href,
      viewport: { w: window.innerWidth, h: window.innerHeight,
                  dpr: window.devicePixelRatio || 1 },
      rect: { x: Math.round(rect.left), y: Math.round(rect.top),
              w: Math.round(rect.width), h: Math.round(rect.height) },
      scroll: { x: Math.round(window.scrollX), y: Math.round(window.scrollY) },
    };
    if (node && node.nodeType === 1) {
      target.selector = cssPath(node);
      target.alternatives = alternatives(node);
      target.tag = node.tagName.toLowerCase();
      target.text = trim(node.textContent || "", 120);
      var src = sourceHint(node);
      if (src.file) target.source_hint = src.file;
      if (src.component) target.component = src.component;
      if (src.scope) target.style_scope = src.scope;
      if (node.getRootNode && node.getRootNode() !== document) target.in_shadow_dom = true;
    }
    return target;
  }

  function trim(s, n) {
    s = (s || "").replace(/\s+/g, " ").trim();
    return s.length > n ? s.slice(0, n) + "..." : s;
  }

  function describe(node) {
    var label = node.tagName.toLowerCase();
    if (node.id) label += "#" + node.id;
    else if (node.classList.length) label += "." + node.classList[0];
    var r = node.getBoundingClientRect();
    return label + "  " + Math.round(r.width) + "x" + Math.round(r.height);
  }

  // Class names emitted by build tools change on every rebuild, so a selector
  // built from them would not survive the fix it is describing.
  var VOLATILE = /^(css-[a-z0-9]{4,}|sc-[A-Za-z0-9]{4,}|[a-z0-9_-]*__[A-Za-z0-9]{5,}|jsx-\d+|svelte-[a-z0-9]{5,})$/;

  function stableClasses(node) {
    return Array.prototype.filter.call(node.classList, function (c) {
      return c && !VOLATILE.test(c) && c.length < 40 && !/^uifb-/.test(c);
    }).slice(0, 2);
  }

  function testId(node) {
    var attrs = ["data-testid", "data-test-id", "data-test", "data-cy", "data-qa"];
    for (var i = 0; i < attrs.length; i++) {
      var v = node.getAttribute && node.getAttribute(attrs[i]);
      if (v) return "[" + attrs[i] + '="' + cssEscape(v) + '"]';
    }
    return null;
  }

  function cssEscape(v) { return String(v).replace(/(["\\])/g, "\\$1"); }

  function uniqueIn(scope, selector) {
    try { return scope.querySelectorAll(selector).length === 1; } catch (e) { return false; }
  }

  function cssPath(node) {
    var scope = (node.getRootNode && node.getRootNode()) || document;
    var tid = testId(node);
    if (tid && uniqueIn(scope, tid)) return tid;
    if (node.id && !/^\d/.test(node.id) && uniqueIn(scope, "#" + CSS_ident(node.id))) {
      return "#" + CSS_ident(node.id);
    }

    var parts = [];
    var current = node;
    while (current && current.nodeType === 1 && parts.length < 6) {
      var step = current.tagName.toLowerCase();
      var own = testId(current);
      if (own) { parts.unshift(own); break; }
      if (current.id && uniqueIn(scope, "#" + CSS_ident(current.id))) {
        parts.unshift("#" + CSS_ident(current.id));
        break;
      }
      var cls = stableClasses(current);
      if (cls.length) step += "." + cls.join(".");
      var parent = current.parentElement;
      if (parent) {
        var sameTag = Array.prototype.filter.call(parent.children, function (c) {
          return c.tagName === current.tagName;
        });
        if (sameTag.length > 1) {
          step += ":nth-of-type(" + (sameTag.indexOf(current) + 1) + ")";
        }
      }
      parts.unshift(step);
      var candidate = parts.join(" > ");
      if (uniqueIn(scope, candidate)) return candidate;
      current = parent;
      if (current && (current.tagName === "BODY" || current.tagName === "HTML")) break;
    }
    return parts.join(" > ");
  }

  function CSS_ident(v) {
    return window.CSS && CSS.escape ? CSS.escape(v) : String(v).replace(/([^\w-])/g, "\\$1");
  }

  function alternatives(node) {
    var out = [];
    var aria = node.getAttribute && node.getAttribute("aria-label");
    if (aria) out.push('[aria-label="' + cssEscape(aria) + '"]');
    var role = node.getAttribute && node.getAttribute("role");
    if (role) out.push('[role="' + cssEscape(role) + '"]');
    var name = node.getAttribute && node.getAttribute("name");
    if (name) out.push("[name=\"" + cssEscape(name) + '"]');
    return out;
  }

  /* Where does this element come from in the source tree?
   *
   * Dev builds of the major frameworks leave the originating file on the DOM
   * node or its component instance. Reading it turns "the third card looks
   * wrong" into a file path, which is the difference between the agent
   * guessing and the agent opening the right file. Every probe is wrapped
   * because these are private fields that come and go between versions - a
   * missing hint is fine, a thrown error inside the reviewer's app is not. */
  function sourceHint(node) {
    var out = {};
    try {
      var current = node;
      while (current && current.nodeType === 1 && !out.file) {
        // Vue 3
        var vc = current.__vueParentComponent;
        if (vc && vc.type) {
          out.file = vc.type.__file || out.file;
          out.component = vc.type.__name || vc.type.name || out.component;
        }
        // Vue 2
        if (!out.file && current.__vue__ && current.__vue__.$options) {
          out.file = current.__vue__.$options.__file || out.file;
          out.component = current.__vue__.$options.name || out.component;
        }
        // Svelte
        if (!out.file && current.__svelte_meta && current.__svelte_meta.loc) {
          out.file = current.__svelte_meta.loc.file;
        }
        // React: the fiber carries a debug source in development builds.
        if (!out.file) {
          for (var key in current) {
            if (key.indexOf("__reactFiber$") !== 0) continue;
            var fiber = current[key];
            var hops = 0;
            while (fiber && hops++ < 12) {
              if (fiber._debugSource && fiber._debugSource.fileName) {
                out.file = fiber._debugSource.fileName;
                if (fiber._debugSource.lineNumber) {
                  out.file += ":" + fiber._debugSource.lineNumber;
                }
                break;
              }
              if (!out.component && typeof fiber.type === "function") {
                out.component = fiber.type.displayName || fiber.type.name;
              }
              fiber = fiber._debugOwner || fiber.return;
            }
            break;
          }
        }
        // Vue single-file-component scope id: not a path, but a token that
        // greps straight to the right .vue file.
        if (!out.scope && current.attributes) {
          for (var i = 0; i < current.attributes.length; i++) {
            var an = current.attributes[i].name;
            if (/^data-v-[0-9a-f]{6,}$/.test(an)) { out.scope = an; break; }
          }
        }
        current = current.parentElement;
      }
    } catch (e) { /* private framework internals; never worth breaking on */ }
    if (out.file) out.file = String(out.file).replace(/^.*?\/(src|app|pages|components)\//, "$1/");
    return out;
  }

  /* ------------------------------------------------------------------ api */

  function createItem(body, kind, target, rect) {
    fetch(API + "/items", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: body, kind: kind, target: target, status: "open" }),
    }).then(function (r) { return r.json(); }).then(function (item) {
      // Plain object, not the live DOMRect: this crosses postMessage to the
      // shell, and the shell needs the numbers to crop a screenshot.
      post({
        type: "uifb:created", item: item,
        rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
        scroll: { x: window.scrollX, y: window.scrollY },
      });
      toast("Saved " + item.id + " - open the rail to send it");
      refresh();
    }).catch(function () { toast("Could not save - is the review server still running?"); });
  }

  function refresh() {
    fetch(API + "/items?status=active").then(function (r) { return r.json(); })
      .then(function (data) {
        state.items = data.items || [];
        var active = state.items.length;
        countBadge.textContent = String(active);
        countBadge.classList.toggle("uifb-hot", active > 0);
        renderPins();
      }).catch(function () {});
  }

  /* ----------------------------------------------------------------- pins */

  var pins = [];
  function renderPins() {
    pins.forEach(function (p) { if (p.parentNode) p.parentNode.removeChild(p); });
    pins = [];
    if (!state.pinsVisible) return;
    var here = location.pathname;
    state.items.forEach(function (item, idx) {
      var t = item.target || {};
      if ((t.route || "").split("?")[0] !== here) return;
      var node = null;
      try { node = t.selector ? document.querySelector(t.selector) : null; } catch (e) {}
      var rect = node ? node.getBoundingClientRect()
                      : (t.rect ? { left: t.rect.x, top: t.rect.y - (window.scrollY - ((t.scroll || {}).y || 0)),
                                    width: t.rect.w, height: t.rect.h } : null);
      if (!rect) return;
      if (rect.top < -40 || rect.top > window.innerHeight + 40) return;
      var pin = el("div", "uifb-pin uifb-s-" + (item.status || "open"), String(idx + 1));
      pin.title = item.id + " - " + (item.title || "");
      pin.style.left = Math.max(2, rect.left - 8) + "px";
      pin.style.top = Math.max(2, rect.top - 8) + "px";
      pin.onclick = function () {
        toast(item.id + " [" + item.status + "] " + (item.title || ""));
        post({ type: "uifb:focus", id: item.id });
      };
      layer.appendChild(pin);
      pins.push(pin);
    });
  }

  var repositionTimer = null;
  function scheduleRender() {
    clearTimeout(repositionTimer);
    repositionTimer = setTimeout(renderPins, 60);
  }
  window.addEventListener("scroll", scheduleRender, true);
  window.addEventListener("resize", scheduleRender);

  /* ---------------------------------------------------------------- toast */

  var toastNode = null, toastTimer = null;
  function toast(text) {
    if (toastNode && toastNode.parentNode) toastNode.parentNode.removeChild(toastNode);
    toastNode = el("div", "uifb-toast", text);
    layer.appendChild(toastNode);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      if (toastNode && toastNode.parentNode) toastNode.parentNode.removeChild(toastNode);
    }, 2600);
  }

  /* --------------------------------------------------------- shell bridge */

  function post(msg) {
    if (state.inShell) {
      try { window.parent.postMessage(Object.assign({ uifb: true }, msg), "*"); } catch (e) {}
    }
  }

  window.addEventListener("message", function (e) {
    var msg = e.data;
    if (!msg || !msg.uifb) return;
    if (msg.type === "uifb:setMode") setMode(msg.mode);
    if (msg.type === "uifb:refresh") refresh();
    if (msg.type === "uifb:reveal") reveal(msg.item);
    if (msg.type === "uifb:ping") post({ type: "uifb:pong", route: location.pathname });
  });

  function reveal(item) {
    var t = (item && item.target) || {};
    var node = null;
    try { node = t.selector ? document.querySelector(t.selector) : null; } catch (e) {}
    if (node) {
      node.scrollIntoView({ behavior: "smooth", block: "center" });
      setTimeout(function () { flash(node.getBoundingClientRect()); }, 320);
    } else if (t.rect) {
      window.scrollTo({ left: (t.scroll || {}).x || 0, top: (t.scroll || {}).y || 0,
                        behavior: "smooth" });
      setTimeout(function () {
        flash({ left: t.rect.x, top: t.rect.y, width: t.rect.w, height: t.rect.h });
      }, 320);
      toast("Element no longer matches - showing the recorded area");
    } else {
      toast("Nothing to reveal for " + (item && item.id));
    }
  }

  function flash(rect) {
    var f = el("div", "uifb-flash");
    f.style.left = rect.left + "px";
    f.style.top = rect.top + "px";
    f.style.width = rect.width + "px";
    f.style.height = rect.height + "px";
    layer.appendChild(f);
    setTimeout(function () { if (f.parentNode) f.parentNode.removeChild(f); }, 2900);
  }

  /* ---------------------------------------------------------------- start */

  refresh();
  post({ type: "uifb:ready", route: location.pathname + location.search });
  setInterval(refresh, 15000);
})();
