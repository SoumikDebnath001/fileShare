/* fileShare — client logic. Vanilla JS, no dependencies. */
(function () {
  "use strict";

  var FILES = [];
  try { FILES = JSON.parse(document.getElementById("fileData").textContent) || []; }
  catch (e) { FILES = []; }

  var CAT_ICON = { video: "🎬", audio: "🎵", document: "📄", image: "🖼️" };

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function url(path, name) { return path + "/" + encodeURIComponent(name); }

  /* ---------- generic slider toggle (pill follows active button) ---------- */
  function initSegmented(el, onChange) {
    if (!el) return;
    var segs = el.querySelectorAll(".seg");
    el.style.setProperty("--n", segs.length);
    function activate(i) {
      el.style.setProperty("--i", i);
      segs.forEach(function (s, j) { s.classList.toggle("active", j === i); });
      if (onChange) onChange(segs[i], i);
    }
    segs.forEach(function (s, i) {
      s.addEventListener("click", function () { activate(i); });
    });
    activate(0);
    el.activate = activate;
    return el;
  }

  /* ---------- bottom nav ---------- */
  var nav = document.getElementById("nav");
  var navBtns = nav.querySelectorAll(".navbtn");
  nav.style.setProperty("--n", navBtns.length);
  var views = {
    home: document.getElementById("view-home"),
    upload: document.getElementById("view-upload"),
    files: document.getElementById("view-files")
  };
  function showView(name) {
    var idx = 0;
    navBtns.forEach(function (b, i) {
      var on = b.dataset.view === name;
      b.classList.toggle("active", on);
      if (on) idx = i;
    });
    nav.style.setProperty("--i", idx);
    Object.keys(views).forEach(function (k) {
      views[k].hidden = k !== name;
      if (k === name) views[k].classList.remove("view"), void views[k].offsetWidth, views[k].classList.add("view");
    });
    window.scrollTo(0, 0);
  }
  navBtns.forEach(function (b) {
    b.addEventListener("click", function () { showView(b.dataset.view); });
  });

  /* dashboard stat cards jump straight to a category in Files */
  document.querySelectorAll(".stat[data-jump]").forEach(function (card) {
    card.addEventListener("click", function () {
      showView("files");
      var i = ["image", "video", "audio", "document"].indexOf(card.dataset.jump);
      if (i >= 0) catToggle.activate(i);
    });
  });

  /* ---------- upload type toggle controls the file picker ---------- */
  var fileInput = document.getElementById("fileInput");
  initSegmented(document.getElementById("upToggle"), function (seg) {
    fileInput.setAttribute("accept", seg.dataset.accept);
  });

  /* ---------- Files: category + extension filtering ---------- */
  var currentCat = "image";
  var currentExt = "all";
  var fileArea = document.getElementById("fileArea");
  var extChips = document.getElementById("extChips");

  var catToggle = initSegmented(document.getElementById("catToggle"), function (seg) {
    currentCat = seg.dataset.cat;
    currentExt = "all";
    buildChips();
    render();
  });

  function inCat() { return FILES.filter(function (f) { return f.category === currentCat; }); }

  function buildChips() {
    var exts = {};
    inCat().forEach(function (f) { if (f.ext) exts[f.ext] = (exts[f.ext] || 0) + 1; });
    var keys = Object.keys(exts).sort();
    var html = '<button class="chip active" data-ext="all">All</button>';
    keys.forEach(function (k) {
      html += '<button class="chip" data-ext="' + esc(k) + '">.' + esc(k) + " · " + exts[k] + "</button>";
    });
    extChips.innerHTML = keys.length ? html : "";
    extChips.querySelectorAll(".chip").forEach(function (c) {
      c.addEventListener("click", function () {
        currentExt = c.dataset.ext;
        extChips.querySelectorAll(".chip").forEach(function (x) { x.classList.remove("active"); });
        c.classList.add("active");
        render();
      });
    });
  }

  function render() {
    var list = inCat().filter(function (f) { return currentExt === "all" || f.ext === currentExt; });
    if (!list.length) {
      fileArea.innerHTML = '<div class="empty"><span class="big">🗂️</span>No ' + esc(currentCat) + " files yet.</div>";
      return;
    }
    fileArea.innerHTML = currentCat === "image" ? imageGrid(list) : rowList(list);
    wireActions();
  }

  function metaLine(f) {
    return '<div class="row-meta"><span>' + esc(f.modified) + "</span><span>⬇ " +
      f.downloads + "</span><span>" + esc(f.size) + "</span></div>";
  }

  function imageGrid(list) {
    var h = '<div class="grid">';
    list.forEach(function (f) {
      h += '<div class="tile" data-img="' + esc(url("/view", f.name)) + '">' +
        '<img loading="lazy" src="' + esc(url("/view", f.name)) + '" alt="' + esc(f.name) + '">' +
        '<form class="del-form" method="post" action="' + esc(url("/delete", f.name)) +
          '" data-name="' + esc(f.name) + '"><button class="del act danger" type="submit">✕</button></form>' +
        '<div class="tile-info">' + esc(f.size) + " · ⬇ " + f.downloads + "</div></div>";
    });
    return h + "</div>";
  }

  function rowList(list) {
    var h = '<div class="rows">';
    list.forEach(function (f) {
      var canView = f.category === "document" || f.category === "audio";
      h += '<div class="row glass"><div class="row-ico">' + (CAT_ICON[f.category] || "📄") + "</div>" +
        '<div class="row-main"><div class="row-name">' + esc(f.name) + "</div>" + metaLine(f) + "</div>" +
        '<div class="row-actions">' +
        (canView ? '<a class="act" href="' + esc(url("/view", f.name)) + '" target="_blank" rel="noopener" title="Open">👁</a>' : "") +
        '<a class="act" href="' + esc(url("/download", f.name)) + '" title="Download">⬇</a>' +
        '<form class="act-form del-form" method="post" action="' + esc(url("/delete", f.name)) +
          '" data-name="' + esc(f.name) + '"><button class="act danger" type="submit" title="Delete">🗑</button></form>' +
        "</div></div>";
    });
    return h + "</div>";
  }

  function wireActions() {
    fileArea.querySelectorAll(".tile[data-img]").forEach(function (t) {
      t.addEventListener("click", function (e) {
        if (e.target.closest(".del-form")) return;
        openLightbox(t.dataset.img);
      });
    });
    fileArea.querySelectorAll(".del-form").forEach(function (f) {
      f.addEventListener("submit", function (e) {
        if (!confirm("Delete " + f.dataset.name + "?")) e.preventDefault();
      });
    });
  }

  /* ---------- lightbox ---------- */
  var lb = document.getElementById("lightbox");
  var lbImg = document.getElementById("lbImg");
  function openLightbox(src) { lbImg.src = src; lb.hidden = false; }
  function closeLightbox() { lb.hidden = true; lbImg.src = ""; }
  document.getElementById("lbClose").addEventListener("click", closeLightbox);
  lb.addEventListener("click", function (e) { if (e.target === lb) closeLightbox(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeLightbox(); });

  /* ---------- upload (drag/drop + XHR progress) ---------- */
  var form = document.getElementById("uploadForm");
  var drop = document.getElementById("drop");
  var dropText = document.getElementById("dropText");
  var progress = document.getElementById("progress");
  var bar = document.getElementById("bar");
  var uploadBtn = document.getElementById("uploadBtn");

  fileInput.addEventListener("change", function () {
    dropText.textContent = fileInput.files.length
      ? fileInput.files.length + " file(s) selected"
      : "Tap to choose files";
  });
  ["dragover", "dragenter"].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("over"); });
  });
  ["dragleave", "drop"].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("over"); });
  });
  drop.addEventListener("drop", function (e) {
    fileInput.files = e.dataTransfer.files;
    fileInput.dispatchEvent(new Event("change"));
  });

  form.addEventListener("submit", function (e) {
    if (!fileInput.files.length) return; // let it post normally / no-op
    e.preventDefault();
    var data = new FormData(form);
    var xhr = new XMLHttpRequest();
    xhr.open("POST", form.action);
    xhr.setRequestHeader("X-Requested-With", "fetch");
    progress.hidden = false; uploadBtn.disabled = true; uploadBtn.textContent = "Uploading…";
    xhr.upload.addEventListener("progress", function (ev) {
      if (ev.lengthComputable) bar.style.width = (ev.loaded / ev.total * 100) + "%";
    });
    xhr.addEventListener("load", function () {
      uploadBtn.textContent = "Done ✓";
      setTimeout(function () { location.reload(); }, 400);
    });
    xhr.addEventListener("error", function () {
      uploadBtn.disabled = false; uploadBtn.textContent = "Upload";
      alert("Upload failed.");
    });
    xhr.send(data);
  });

  /* ---------- init ---------- */
  buildChips();
  render();
  setTimeout(function () { var f = document.getElementById("flash"); if (f) f.style.display = "none"; }, 4000);
})();
