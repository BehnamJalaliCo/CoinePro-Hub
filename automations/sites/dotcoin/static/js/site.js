/* DotCoin.me: small, dependency-free behaviour. Content is visible without this file. */
(function () {
  "use strict";
  var d = document, root = d.documentElement, w = window;
  var reduce = w.matchMedia && w.matchMedia("(prefers-reduced-motion: reduce)");
  var still = function () { return !!(reduce && reduce.matches); };
  var FA = "۰۱۲۳۴۵۶۷۸۹";
  var fa = function (n) { return String(n).replace(/\d/g, function (c) { return FA[c]; }); };
  var $$ = function (s, el) { return Array.prototype.slice.call((el || d).querySelectorAll(s)); };

  /* theme: the head script set it; the button flips and remembers it */
  function setTheme(t, save) {
    root.setAttribute("data-theme", t);
    if (save) { try { localStorage.setItem("dc-theme", t); } catch (e) {} }
    d.dispatchEvent(new Event("dc-theme"));
  }
  $$(".theme-btn").forEach(function (b) {
    b.addEventListener("click", function () { setTheme(root.getAttribute("data-theme") === "dark" ? "light" : "dark", true); });
  });
  if (w.matchMedia) {
    var mq = w.matchMedia("(prefers-color-scheme: dark)");
    var follow = function (e) { var s = null; try { s = localStorage.getItem("dc-theme"); } catch (x) {} if (!s) setTheme(e.matches ? "dark" : "light", false); };
    if (mq.addEventListener) mq.addEventListener("change", follow);
  }

  /* header state + reading progress */
  var hdr = d.querySelector(".hdr"), bar = d.querySelector(".progress"), art = d.querySelector(".art-body");
  var ticking = false;
  function onScroll() {
    ticking = false;
    var y = w.scrollY || 0;
    if (hdr) hdr.classList.toggle("scrolled", y > 12);
    if (bar && art && d.body.classList.contains("p-article")) {
      var r = art.getBoundingClientRect(), total = r.height - w.innerHeight * 0.6;
      var p = Math.min(1, Math.max(0, -r.top / Math.max(1, total)));
      bar.style.setProperty("--read", p.toFixed(4));
    }
  }
  w.addEventListener("scroll", function () { if (!ticking) { ticking = true; w.requestAnimationFrame(onScroll); } }, { passive: true });
  onScroll();

  /* mobile drawer */
  var mb = d.querySelector(".menu-btn"), drawer = d.getElementById("drawer");
  function closeDrawer() { if (!drawer || drawer.hidden) return; drawer.hidden = true; mb.setAttribute("aria-expanded", "false"); d.body.classList.remove("drawer-open"); }
  if (mb && drawer) {
    mb.addEventListener("click", function () {
      var open = drawer.hidden;
      drawer.hidden = !open; mb.setAttribute("aria-expanded", String(open)); d.body.classList.toggle("drawer-open", open);
    });
    d.addEventListener("keydown", function (e) { if (e.key === "Escape") closeDrawer(); });
    $$("a", drawer).forEach(function (a) { a.addEventListener("click", closeDrawer); });
  }

  /* scroll reveal: only what starts below the fold is held back; everything else stays at rest */
  if (!still() && "IntersectionObserver" in w) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
    }, { rootMargin: "0px 0px -6% 0px" });
    var vh = w.innerHeight;
    $$(".rv").forEach(function (el) {
      var box = el.parentElement;  /* items of a sideways carousel (phone) stay at rest */
      if (box && box.scrollWidth > box.clientWidth + 4) return;
      if (el.getBoundingClientRect().top > vh * 0.95) { el.classList.add("rv-wait"); io.observe(el); }
    });
    w.setTimeout(function () { $$(".rv-wait:not(.in)").forEach(function (el) { if (el.getBoundingClientRect().top < w.innerHeight) el.classList.add("in"); }); }, 2500);
  }

  /* table of contents: closed on phones, current section marked */
  var toc = d.querySelector(".toc details");
  if (toc && w.innerWidth < 1080) toc.removeAttribute("open");
  var tocLinks = $$(".toc a");
  if (tocLinks.length && "IntersectionObserver" in w) {
    var map = {};
    tocLinks.forEach(function (a) { map[a.getAttribute("href").slice(1)] = a; });
    var tio = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (e.isIntersecting) { tocLinks.forEach(function (a) { a.classList.remove("on"); }); var a = map[e.target.id]; if (a) a.classList.add("on"); }
      });
    }, { rootMargin: "-20% 0px -70% 0px" });
    Object.keys(map).forEach(function (id) { var h = d.getElementById(id); if (h) tio.observe(h); });
  }

  /* today's lesson: a stepped, swipeable lesson */
  $$("[data-stepper]").forEach(function (st) {
    var slides = $$(".st-slide", st), bars = $$(".st-bar", st), n = slides.length, i = 0;
    var prev = st.querySelector(".st-prev"), next = st.querySelector(".st-next"), count = st.querySelector(".st-count");
    function go(k) {
      k = Math.max(0, Math.min(n - 1, k));
      if (k === i) return;
      i = k;
      slides.forEach(function (s, j) {
        s.classList.toggle("is-on", j === i); s.classList.toggle("past", j < i); s.classList.toggle("next", j > i);
        s.setAttribute("aria-hidden", j === i ? "false" : "true");
      });
      bars.forEach(function (b, j) { b.classList.toggle("is-on", j === i); b.classList.toggle("done", j < i); });
      st.style.setProperty("--p", ((i + 1) / n).toFixed(4));
      if (count) count.textContent = fa(i + 1) + " / " + fa(n);
      if (prev) prev.disabled = i === 0;
      if (next) next.disabled = i === n - 1;
    }
    slides.forEach(function (s, j) { if (j) s.setAttribute("aria-hidden", "true"); });
    if (prev) prev.addEventListener("click", function () { go(i - 1); });
    if (next) next.addEventListener("click", function () { go(i + 1); });
    bars.forEach(function (b) { b.addEventListener("click", function () { go(+b.getAttribute("data-go")); }); });
    st.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft") { go(i + 1); e.preventDefault(); }
      if (e.key === "ArrowRight") { go(i - 1); e.preventDefault(); }
    });
    var x0 = null, y0 = 0;
    st.addEventListener("pointerdown", function (e) { if (e.pointerType !== "mouse") { x0 = e.clientX; y0 = e.clientY; } });
    st.addEventListener("pointerup", function (e) {
      if (x0 === null) return;
      var dx = e.clientX - x0, dy = e.clientY - y0; x0 = null;
      if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) go(i + (dx > 0 ? 1 : -1));
    });
  });

  /* learn: filter by pillar (the hash keeps the choice) */
  var chips = $$(".fchip");
  if (chips.length) {
    var cards = $$("[data-filter-scope] .card"), ups = $$(".up li"), empty = d.querySelector(".cards-learn + .empty");
    var apply = function (f) {
      if (!chips.some(function (c) { return c.getAttribute("data-f") === f; })) f = "all";
      chips.forEach(function (c) { var on = c.getAttribute("data-f") === f; c.classList.toggle("is-on", on); c.setAttribute("aria-pressed", String(on)); });
      var shown = 0;
      cards.forEach(function (c) { var ok = f === "all" || c.getAttribute("data-pillar") === f; c.hidden = !ok; if (ok) { shown++; c.classList.add("in"); } });
      ups.forEach(function (u) { u.hidden = !(f === "all" || u.getAttribute("data-pillar") === f); });
      if (empty) empty.hidden = shown > 0;
    };
    chips.forEach(function (c) {
      c.addEventListener("click", function () {
        var f = c.getAttribute("data-f"); apply(f);
        try { history.replaceState(null, "", f === "all" ? location.pathname : "#" + f); } catch (e) {}
      });
    });
    if (location.hash) apply(decodeURIComponent(location.hash.slice(1)));
  }

  /* copy a referral code */
  $$("[data-copy]").forEach(function (b) {
    b.addEventListener("click", function () {
      var t = b.getAttribute("data-copy");
      var done = function () { b.classList.add("ok"); w.setTimeout(function () { b.classList.remove("ok"); }, 1600); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(t).then(done, done);
      else { var ta = d.createElement("textarea"); ta.value = t; d.body.appendChild(ta); ta.select(); try { d.execCommand("copy"); } catch (e) {} ta.remove(); done(); }
    });
  });

  /* glossary search */
  var q = d.getElementById("q");
  if (q) {
    var norm = function (s) { return s.toLowerCase().replace(/[‌\s\-]/g, "").replace(/ي/g, "ی").replace(/ك/g, "ک").replace(/[آأإ]/g, "ا"); };
    var terms = $$(".term"), groups = $$(".gl-g"), cnt = d.querySelector(".gl-count"), none = d.querySelector(".gl + .empty");
    terms.forEach(function (t) { t._k = norm(t.textContent); });
    q.addEventListener("input", function () {
      var v = norm(q.value), shown = 0;
      terms.forEach(function (t) { var ok = !v || t._k.indexOf(v) >= 0; t.hidden = !ok; if (ok) shown++; });
      groups.forEach(function (g) { g.hidden = !$$(".term", g).some(function (t) { return !t.hidden; }); });
      if (cnt) cnt.textContent = fa(shown) + " واژه";
      if (none) none.hidden = shown > 0;
    });
  }

  /* the live chain of blocks (home): mine, link, tamper, heal */
  var cv = d.querySelector("canvas.chain");
  if (cv && cv.getContext) chain(cv);

  function chain(cv) {
    var ctx = cv.getContext("2d"), msg = d.querySelector(".chain-msg");
    var W = 0, H = 0, dpr = 1, S = 100, G = 46, blocks = [], height = 0, shift = 0, shiftFrom = 0, shiftT = 1;
    var col = {}, hover = -1, running = false, visible = true, last = 0, nextMine = 0, broken = -1, healAt = 0;
    var HEX = "0123456789abcdef";
    function hex(n) { var s = ""; for (var k = 0; k < n; k++) s += HEX[(Math.random() * 16) | 0]; return s; }
    function colors() {
      var cs = getComputedStyle(cv);
      ["--chain-bg", "--chain-fg", "--chain-dim", "--chain-bad", "--chain-text", "--chain-ink"].forEach(function (k) { col[k.slice(8)] = cs.getPropertyValue(k).trim(); });
    }
    function size() {
      var r = cv.getBoundingClientRect(); dpr = Math.min(2, w.devicePixelRatio || 1);
      W = r.width; H = r.height; cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
      S = W < 640 ? 76 : 104; G = W < 640 ? 34 : 50;
      var need = Math.ceil(W / (S + G)) + 2;
      while (blocks.length < need) addBlock(true);
      draw(performance.now());
    }
    function addBlock(instant) {
      var prev = blocks.length ? blocks[blocks.length - 1].hash : "0000000000";
      blocks.push({ n: height++, hash: hex(10), prev: prev, born: instant ? -1e9 : performance.now(), tamper: 0 });
      if (!instant) { shiftFrom = shift - (S + G); shift = shiftFrom; shiftT = 0; }
      if (blocks.length > 40) blocks.shift();
    }
    function ease(t) { return 1 - Math.pow(1 - t, 4); }
    function rr(x, y, w2, h2, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w2, y, x + w2, y + h2, r); ctx.arcTo(x + w2, y + h2, x, y + h2, r); ctx.arcTo(x, y + h2, x, y, r); ctx.arcTo(x, y, x + w2, y, r); ctx.closePath(); }
    function bx(idx) { /* newest block on the left, older to the right (RTL time) */
      var fromNewest = blocks.length - 1 - idx;
      return W * 0.12 + fromNewest * (S + G) - shift;
    }
    function draw(now) {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      var y = H * 0.5 - S * 0.5 - 6;
      if (shiftT < 1) { shiftT = Math.min(1, shiftT + 0.035); shift = shiftFrom * (1 - ease(shiftT)); }
      ctx.lineCap = "round";
      for (var i = blocks.length - 1; i >= 0; i--) {
        var b = blocks[i], x = bx(i);
        if (x > W + S || x < -S * 2) continue;
        var bad = broken >= 0 && i >= broken;
        var age = (now - b.born) / 900, mining = age < 1;
        var c = bad ? col.bad : col.fg;
        var lift = i === hover ? -6 : 0;
        /* link to the previous (older) block, on the right */
        if (i > 0) {
          var x2 = bx(i - 1), gapBad = broken >= 0 && i === broken + 0 && false;
          ctx.strokeStyle = bad ? col.bad : col.dim; ctx.lineWidth = 3;
          var lx = x + S, ly = y + S * 0.5;
          if (bad && i === broken + 1) { /* the broken link */
            ctx.setLineDash([4, 8]);
          } else ctx.setLineDash([]);
          ctx.beginPath(); ctx.moveTo(lx + 2, ly - 8); ctx.lineTo(x2 - 2, ly - 8); ctx.moveTo(lx + 2, ly + 8); ctx.lineTo(x2 - 2, ly + 8); ctx.stroke();
          ctx.setLineDash([]);
        }
        ctx.save();
        ctx.translate(0, lift);
        if (mining) {
          var a = ease(Math.max(0, age));
          ctx.globalAlpha = 0.35 + 0.65 * a;
          ctx.setLineDash([6, 7]); ctx.lineDashOffset = -now / 30;
        }
        rr(x, y, S, S, 16);
        var flash = !mining && age < 1.6 ? 1 - (age - 1) / 0.6 : 0;
        if (flash > 0) { ctx.fillStyle = c; ctx.globalAlpha = flash * 0.9; ctx.fill(); ctx.globalAlpha = 1; }
        if (i === hover && !mining) { ctx.fillStyle = col.dim; ctx.fill(); }
        ctx.strokeStyle = c; ctx.lineWidth = 2.5; ctx.stroke(); ctx.setLineDash([]);
        var tc = flash > 0.5 ? col.ink : (bad ? col.bad : col.text);
        ctx.fillStyle = bad ? col.bad : col.fg;
        ctx.font = "800 " + (S < 90 ? 12 : 14) + "px Yekan, sans-serif"; ctx.textAlign = "right"; ctx.direction = "rtl";
        ctx.fillText("بلوک " + fa(b.n), x + S - 12, y + 24);
        ctx.fillStyle = tc; ctx.textAlign = "left"; ctx.direction = "ltr";
        ctx.font = (S < 90 ? 15 : 19) + "px Anton, Impact, sans-serif";
        var h = mining ? hex(6) : (b.tamper ? b.tamper : b.hash).slice(0, 6);
        ctx.fillText(h.toUpperCase(), x + 12, y + S * 0.62);
        ctx.globalAlpha = 0.55; ctx.font = (S < 90 ? 10 : 11) + "px Anton, Impact, sans-serif";
        ctx.fillText("PREV " + b.prev.slice(0, 4).toUpperCase(), x + 12, y + S - 14);
        ctx.restore();
        ctx.globalAlpha = 1;
      }
    }
    function loop(now) {
      if (!running) return;
      if (!still() && now > nextMine && broken < 0) { addBlock(false); nextMine = now + 3600; }
      if (broken >= 0 && now > healAt) heal();
      draw(now);
      w.requestAnimationFrame(loop);
    }
    function start() { if (running || !visible) return; running = true; w.requestAnimationFrame(loop); }
    function stop() { running = false; }
    function heal() {
      if (broken < 0) return;
      blocks[broken].tamper = 0; broken = -1;
      if (msg) msg.textContent = "";
    }
    function hit(e) {
      var r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top, y = H * 0.5 - S * 0.5 - 6;
      for (var i = 0; i < blocks.length; i++) { var x = bx(i); if (mx >= x && mx <= x + S && my >= y - 8 && my <= y + S + 8) return i; }
      return -1;
    }
    cv.addEventListener("pointermove", function (e) { var h = hit(e); if (h !== hover) { hover = h; if (!running) draw(performance.now()); } });
    cv.addEventListener("pointerleave", function () { hover = -1; if (!running) draw(performance.now()); });
    cv.addEventListener("click", function (e) {
      var i = hit(e); if (i < 0) return;
      if (broken >= 0) heal();
      broken = i; blocks[i].tamper = hex(10); healAt = performance.now() + 3200;
      if (msg) msg.textContent = i === blocks.length - 1 ? "این تازه‌ترین بلوک است؛ اثر انگشتش عوض شد و شبکه آن را نمی‌پذیرد" :
        "بلوک " + fa(blocks[i].n) + " تغییر کرد؛ اثر انگشتش عوض شد و " + fa(blocks.length - 1 - i) + " بلوک بعدی دیگر به آن وصل نیستند";
      if (!running) { draw(performance.now()); w.setTimeout(function () { heal(); draw(performance.now()); }, 3200); }
    });
    colors(); size();
    d.addEventListener("dc-theme", function () { colors(); draw(performance.now()); });
    var rt; w.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(size, 120); });
    if (d.fonts && d.fonts.ready) d.fonts.ready.then(function () { draw(performance.now()); });
    if ("IntersectionObserver" in w) {
      new IntersectionObserver(function (es) { visible = es[0].isIntersecting; if (visible) start(); else stop(); }).observe(cv);
    } else start();
    d.addEventListener("visibilitychange", function () { if (d.hidden) stop(); else start(); });
    nextMine = performance.now() + 1400;
  }
})();
