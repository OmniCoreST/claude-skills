/* Review shell: the app under review on the left, the feedback ledger on the
 * right. The shell never reaches into the app's code - it talks to the injected
 * overlay over postMessage and to the store over the local API, so the same
 * rail works for a Vue app, a Django template or a static site.
 */
(function () {
  "use strict";

  var API = "/__uifb/api";
  var $ = function (id) { return document.getElementById(id); };

  var app = $("app");
  var listEl = $("list");
  var state = {
    config: {},
    items: [],
    filter: "active",
    query: "",
    expanded: {},
    focusId: null,
    stream: null,
  };

  var FILTERS = [
    { key: "active", label: "Active", match: function (i) {
        return ["open", "sent", "in_progress"].indexOf(i.status) >= 0; } },
    { key: "open", label: "Draft", match: function (i) { return i.status === "open"; } },
    { key: "sent", label: "With AI", match: function (i) {
        return i.status === "sent" || i.status === "in_progress"; } },
    { key: "done", label: "Closed", match: function (i) {
        return i.status === "done" || i.status === "wont_fix"; } },
    { key: "all", label: "All", match: function () { return true; } },
  ];

  var WIDTHS = [
    { label: "Phone", w: 390 },
    { label: "Tablet", w: 820 },
    { label: "Laptop", w: 1280 },
    { label: "Full", w: 0 },
  ];

  /* ------------------------------------------------------------------ boot */

  // Land on a specific page when the review URL carries one:
  //   /__uifb/review#/docs/architecture.html
  // Without this the frame always opens at "/", which on a static site is a
  // directory listing rather than the page the reviewer asked to look at.
  // Using the hash rather than a server setting keeps the URL shareable and
  // lets the reviewer bookmark the exact page they were reviewing.
  var startPath = decodeURIComponent((location.hash || "").replace(/^#/, ""));
  if (startPath.charAt(0) === "/") app.src = startPath;

  fetch(API + "/config").then(function (r) { return r.json(); }).then(function (cfg) {
    state.config = cfg;
    $("project").textContent = cfg.project || "review";
    document.title = (cfg.project || "review") + " - UI review";
    renderFoot();
  });

  refresh();
  subscribe();

  /* --------------------------------------------------------------- toolbar */

  $("mode-pick").onclick = function () { toggleMode("pick", this); };
  $("mode-region").onclick = function () { toggleMode("region", this); };

  function toggleMode(mode, btn) {
    var turningOn = !btn.classList.contains("on");
    $("mode-pick").classList.remove("on");
    $("mode-region").classList.remove("on");
    if (turningOn) btn.classList.add("on");
    toApp({ type: "uifb:setMode", mode: turningOn ? mode : "idle" });
  }

  $("reload").onclick = function () { app.contentWindow.location.reload(); };
  $("back").onclick = function () { try { app.contentWindow.history.back(); } catch (e) {} };

  $("route").addEventListener("keydown", function (e) {
    if (e.key !== "Enter") return;
    var value = this.value.trim() || "/";
    app.src = value.charAt(0) === "/" ? value : "/" + value;
  });

  $("toggle-rail").onclick = function () { document.body.classList.toggle("rail-hidden"); };

  var widthsEl = $("widths");
  WIDTHS.forEach(function (preset) {
    var btn = document.createElement("button");
    btn.className = "btn ghost tiny";
    btn.textContent = preset.label;
    btn.onclick = function () {
      var wrap = $("frameWrap");
      Array.prototype.forEach.call(widthsEl.children, function (c) { c.classList.remove("on"); });
      if (preset.w) {
        btn.classList.add("on");
        wrap.classList.add("constrained");
        wrap.style.width = preset.w + "px";
        wrap.style.margin = "0 auto";
      } else {
        wrap.classList.remove("constrained");
        wrap.style.width = "100%";
        wrap.style.margin = "0";
      }
    };
    widthsEl.appendChild(btn);
  });

  document.addEventListener("keydown", function (e) {
    if (e.altKey && /^[mM]$/.test(e.key)) toggleMode("pick", $("mode-pick"));
    if (e.altKey && /^[rR]$/.test(e.key)) toggleMode("region", $("mode-region"));
    if (e.key === "Escape") {
      $("mode-pick").classList.remove("on");
      $("mode-region").classList.remove("on");
    }
  });

  /* --------------------------------------------------------- route display */

  function syncRoute() {
    try {
      var loc = app.contentWindow.location;
      var here = loc.pathname + loc.search + loc.hash;
      if (document.activeElement !== $("route") && $("route").value !== here) {
        $("route").value = here;
      }
    } catch (e) { /* mid-navigation */ }
  }
  setInterval(syncRoute, 700);
  app.addEventListener("load", syncRoute);

  /* -------------------------------------------------------------- messages */

  window.addEventListener("message", function (e) {
    var msg = e.data;
    if (!msg || !msg.uifb) return;
    if (msg.type === "uifb:created") {
      refresh();
      captureFor(msg.item, msg.rect);
      state.expanded[msg.item.id] = true;
    }
    if (msg.type === "uifb:focus") {
      state.focusId = msg.id;
      state.expanded[msg.id] = true;
      render();
      var card = document.querySelector('[data-id="' + msg.id + '"]');
      if (card) card.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    if (msg.type === "uifb:mode" && msg.mode === "idle") {
      $("mode-pick").classList.remove("on");
      $("mode-region").classList.remove("on");
    }
    if (msg.type === "uifb:ready") syncRoute();
  });

  function toApp(msg) {
    try { app.contentWindow.postMessage(Object.assign({ uifb: true }, msg), "*"); }
    catch (e) {}
  }

  /* ------------------------------------------------------------------ data */

  function refresh() {
    // Config rides along because hooks can be installed while this page is
    // open, and a footer that keeps saying "not installed" after the fact
    // teaches the reviewer to distrust the rail.
    return Promise.all([
      fetch(API + "/items?status=all").then(function (r) { return r.json(); }),
      fetch(API + "/config").then(function (r) { return r.json(); }),
    ]).then(function (res) {
      state.items = (res[0].items || []).slice().reverse();
      state.config = res[1];
      render();
    }).catch(function () { toast("Review server unreachable"); });
  }

  function subscribe() {
    try {
      var es = new EventSource(API + "/events");
      // The agent moves items to in_progress and done from the CLI while the
      // reviewer watches; without this the rail would look frozen exactly when
      // the work is happening.
      es.onmessage = function () { refresh(); };
      es.onerror = function () { setTimeout(subscribe, 4000); es.close(); };
    } catch (e) {}
    // Belt and braces: a dropped stream must not leave the reviewer staring at
    // a rail that will never move again.
    if (!subscribe.polling) {
      subscribe.polling = setInterval(refresh, 12000);
    }
  }

  function patch(id, changes) {
    return fetch(API + "/items/" + id, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    }).then(refresh);
  }

  /* ---------------------------------------------------------------- render */

  $("search").addEventListener("input", function () {
    state.query = this.value.toLowerCase();
    render();
  });

  function visible() {
    var f = FILTERS.filter(function (x) { return x.key === state.filter; })[0] || FILTERS[0];
    return state.items.filter(function (i) {
      if (!f.match(i)) return false;
      if (!state.query) return true;
      var hay = [i.id, i.title, i.body, (i.target || {}).selector, (i.target || {}).route,
                 (i.target || {}).source_hint].join(" ").toLowerCase();
      return hay.indexOf(state.query) >= 0;
    });
  }

  function renderFilters() {
    var box = $("filters");
    box.textContent = "";
    FILTERS.forEach(function (f) {
      var n = state.items.filter(f.match).length;
      var chip = document.createElement("button");
      chip.className = "chip" + (state.filter === f.key ? " on" : "");
      chip.innerHTML = f.label + '<span class="n">' + n + "</span>";
      chip.onclick = function () { state.filter = f.key; render(); };
      box.appendChild(chip);
    });
  }

  function render() {
    renderFilters();
    renderFoot();
    var rows = visible();
    listEl.textContent = "";
    if (!rows.length) {
      var empty = document.createElement("div");
      empty.className = "empty";
      empty.innerHTML = state.items.length
        ? "Nothing matches this filter."
        : "No feedback yet.<br><br>Hit <b>Mark element</b> and click something in the app, "
          + "or <b>Draw region</b> and drag a box over an area.";
      listEl.appendChild(empty);
      return;
    }
    rows.forEach(function (item) { listEl.appendChild(card(item)); });
  }

  function card(item) {
    var t = item.target || {};
    var node = document.createElement("article");
    node.className = "card"
      + (state.expanded[item.id] ? " open-detail" : "")
      + (state.focusId === item.id ? " focus" : "")
      + (item.status === "done" || item.status === "wont_fix" ? " done" : "");
    node.dataset.id = item.id;

    var top = document.createElement("div");
    top.className = "card-top";
    top.innerHTML =
      '<span class="id">' + item.id + "</span>" +
      '<span class="pill ' + item.status + '">' + item.status.replace("_", " ") + "</span>" +
      '<span class="title"></span>' +
      '<span class="pill kind">' + (item.kind || "change") + "</span>";
    top.querySelector(".title").textContent = item.title || "(no description)";
    top.onclick = function () {
      state.expanded[item.id] = !state.expanded[item.id];
      render();
    };

    var body = document.createElement("div");
    body.className = "card-body";

    if (item.body) {
      var text = document.createElement("div");
      text.className = "text";
      text.textContent = item.body;
      body.appendChild(text);
    }

    if (item.screenshot) {
      var img = document.createElement("img");
      img.className = "shot";
      img.loading = "lazy";
      img.src = "/__uifb/" + item.screenshot + "?v=" + encodeURIComponent(item.updated_at || "");
      img.alt = "screenshot for " + item.id;
      img.onclick = function () {
        $("lightboxImg").src = img.src;
        $("lightbox").hidden = false;
      };
      body.appendChild(img);
    }

    var meta = document.createElement("div");
    meta.className = "meta";
    meta.appendChild(line(t.route || "/", null));
    if (t.selector) meta.appendChild(line(t.selector, "code"));
    if (t.source_hint) meta.appendChild(line("source: " + t.source_hint, "src"));
    if (t.component) meta.appendChild(line("component: " + t.component, "src"));
    if (t.style_scope) meta.appendChild(line("scope attr: " + t.style_scope, "code"));
    if (t.viewport) meta.appendChild(line("viewport " + t.viewport.w + "x" + t.viewport.h, null));
    body.appendChild(meta);

    if ((item.thread || []).length) {
      var thread = document.createElement("div");
      thread.className = "thread";
      item.thread.forEach(function (n) {
        var note = document.createElement("div");
        note.className = "note";
        note.innerHTML = "<b>" + (n.role === "agent" ? "AI" : "you") + "</b> ";
        note.appendChild(document.createTextNode(n.text));
        thread.appendChild(note);
      });
      body.appendChild(thread);
    }

    body.appendChild(actions(item));
    node.append(top, body);
    return node;
  }

  function line(text, cls) {
    var d = document.createElement("div");
    if (cls === "code") {
      var c = document.createElement("code");
      c.textContent = text;
      d.appendChild(c);
    } else {
      if (cls) d.className = cls;
      d.textContent = text;
    }
    return d;
  }

  function actions(item) {
    var box = document.createElement("div");
    box.className = "card-actions";

    box.appendChild(button("Reveal", "ghost", function () {
      var route = (item.target || {}).route;
      var current = "";
      try {
        current = app.contentWindow.location.pathname + app.contentWindow.location.search;
      } catch (e) {}
      if (route && route.split("#")[0] !== current) {
        app.src = route;
        app.addEventListener("load", function once() {
          app.removeEventListener("load", once);
          setTimeout(function () { toApp({ type: "uifb:reveal", item: item }); }, 400);
        });
      } else {
        toApp({ type: "uifb:reveal", item: item });
      }
    }));

    if (item.status === "open") {
      box.appendChild(button("Send this", "primary", function () {
        fetch(API + "/send", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ids: [item.id] }),
        }).then(refresh).then(function () { toast("Handed " + item.id + " to the AI"); });
      }));
      box.appendChild(button("Delete", "ghost", function () {
        fetch(API + "/items/" + item.id, { method: "DELETE" }).then(refresh);
      }));
    } else if (item.status === "sent" || item.status === "in_progress") {
      box.appendChild(button("Mark done", "ghost", function () {
        patch(item.id, { status: "done" });
      }));
      box.appendChild(button("Won't fix", "ghost", function () {
        patch(item.id, { status: "wont_fix" });
      }));
    } else {
      box.appendChild(button("Reopen", "ghost", function () {
        patch(item.id, { status: "sent", delivered_at: null });
      }));
    }
    return box;
  }

  function button(label, cls, fn) {
    var b = document.createElement("button");
    b.className = "btn tiny " + cls;
    b.textContent = label;
    b.onclick = fn;
    return b;
  }

  /* ------------------------------------------------------------------ send */

  function renderFoot() {
    var drafts = state.items.filter(function (i) { return i.status === "open"; }).length;
    var waiting = state.items.filter(function (i) {
      return i.status === "sent" && !i.delivered_at;
    }).length;
    var btn = $("send");
    btn.disabled = drafts === 0;
    btn.textContent = drafts ? "Send " + drafts + " to AI" : "Send to AI";

    var note = $("footNote");
    if (state.config.hooksInstalled) {
      note.innerHTML = waiting
        ? "<b>" + waiting + " waiting.</b> Claude picks these up when it next finishes a step."
        : "Hooks are wired: sent items reach Claude on their own.";
    } else {
      note.innerHTML = "Hooks are not installed - Claude reads sent items the next time you "
        + "say something. Run <b>uifb.py install-hooks</b> for automatic pickup.";
    }
  }

  $("send").onclick = function () {
    fetch(API + "/send", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
    }).then(function (r) { return r.json(); }).then(function (res) {
      toast(res.count + " item" + (res.count === 1 ? "" : "s") + " handed to the AI");
      refresh();
    });
  };

  /* ----------------------------------------------------------- screenshots */

  $("shots").onclick = function () {
    if (state.stream) {
      state.stream.getTracks().forEach(function (t) { t.stop(); });
      state.stream = null;
      $("shots").textContent = "Screenshots: off";
      $("shots").classList.remove("on");
      return;
    }
    // One grant covers the whole session: every later item is cropped from the
    // live stream, so the reviewer is never interrupted by a permission dialog
    // in the middle of writing a comment.
    navigator.mediaDevices.getDisplayMedia({
      video: { displaySurface: "browser" }, preferCurrentTab: true, audio: false,
    }).then(function (stream) {
      state.stream = stream;
      var v = $("grabber");
      v.srcObject = stream;
      return v.play();
    }).then(function () {
      $("shots").textContent = "Screenshots: on";
      $("shots").classList.add("on");
      toast("Pick this tab's own view for the tightest crops");
      state.stream.getVideoTracks()[0].addEventListener("ended", function () {
        state.stream = null;
        $("shots").textContent = "Screenshots: off";
        $("shots").classList.remove("on");
      });
    }).catch(function () {
      toast("Screen capture declined - items keep their coordinates, just no picture");
    });
  };

  function captureFor(item, rect) {
    if (!state.stream || !rect) return;
    var video = $("grabber");
    if (!video.videoWidth) return;
    // Two frames of grace so the composer and highlight are gone from the
    // compositor before the crop is taken.
    requestAnimationFrame(function () { requestAnimationFrame(function () {
      try { crop(item, rect, video); } catch (e) {}
    }); });
  }

  function crop(item, rect, video) {
    var frameBox = app.getBoundingClientRect();
    var sx = video.videoWidth / window.innerWidth;
    var sy = video.videoHeight / window.innerHeight;
    var pad = 28;

    var absX = frameBox.left + rect.left;
    var absY = frameBox.top + rect.top;
    var x = Math.max(0, (absX - pad) * sx);
    var y = Math.max(0, (absY - pad) * sy);
    var w = Math.min(video.videoWidth - x, (rect.width + pad * 2) * sx);
    var h = Math.min(video.videoHeight - y, (rect.height + pad * 2) * sy);
    if (w < 8 || h < 8) return;

    var canvas = $("canvas");
    canvas.width = Math.round(w);
    canvas.height = Math.round(h);
    var ctx = canvas.getContext("2d");
    ctx.drawImage(video, x, y, w, h, 0, 0, canvas.width, canvas.height);

    // Draw the marked area back onto the crop. Padding alone loses the point:
    // the reader has to know which part of the picture the comment is about.
    ctx.strokeStyle = "#7c5cff";
    ctx.lineWidth = Math.max(2, 2 * sx);
    ctx.strokeRect((absX * sx) - x, (absY * sy) - y, rect.width * sx, rect.height * sy);

    canvas.toBlob(function (blob) {
      if (!blob) return;
      fetch(API + "/items/" + item.id + "/screenshot", {
        method: "POST", headers: { "Content-Type": "image/png" }, body: blob,
      }).then(refresh);
    }, "image/png");
  }

  /* ---------------------------------------------------------------- chrome */

  $("lightbox").onclick = function () { this.hidden = true; };

  var toastTimer = null;
  function toast(text) {
    var t = $("toast");
    t.textContent = text;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.hidden = true; }, 3000);
  }
})();
