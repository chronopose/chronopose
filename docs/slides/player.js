// Проигрыватель колоды: deck.json + slides/<id>.html в той же папке.
// Клавиши: → ↓ PgDn пробел — вперёд; ← ↑ PgUp — назад; Home/End; F — полный экран. Номер слайда в адресе: #7.
(async function () {
  const stage = document.getElementById("stage");
  const viewport = document.getElementById("viewport");
  const bar = document.getElementById("bar");
  const count = document.getElementById("count");
  const progress = document.getElementById("progress");
  const W = 1920, H = 1080;

  function fail(msg) {
    document.body.insertAdjacentHTML("beforeend", `<div id="err">${msg}</div>`);
  }

  let deck;
  try {
    deck = await (await fetch("deck.json", { cache: "no-cache" })).json();
  } catch (e) {
    return fail("Не удалось загрузить deck.json. Откройте страницу через GitHub Pages, а не как локальный файл.");
  }
  document.title = deck.title;
  for (const f of Object.values(deck.faces || {})) {
    if (f.href) document.head.insertAdjacentHTML("beforeend", `<link rel="stylesheet" href="${f.href}">`);
  }

  const esc = (s) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
  const CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:";
  function prepare(src) {
    src = src.replace(/<aside[\s\S]*?<\/aside>/gi, "");
    src = src.replace(/<img\b[^>]*src="\/_blob\/[^"]*"[^>]*>/gi, ""); // приватные картинки claude.ai не публикуем
    return src.replace(/<x-embed([^>]*)>([\s\S]*?)<\/x-embed>/gi, (m, attrs, body) => {
      const doc = `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${CSP}">` +
        `<style>html,body{margin:0;padding:0;overflow:hidden;background:transparent}</style></head><body>${body}</body></html>`;
      return `<iframe sandbox="allow-scripts" scrolling="no"${attrs} srcdoc="${esc(doc)}"></iframe>`;
    });
  }

  const order = deck.order;
  const cache = new Map();
  const load = (id) => {
    if (!cache.has(id)) {
      cache.set(id, fetch(`slides/${id}.html`, { cache: "no-cache" }).then((r) => r.text()).then(prepare));
    }
    return cache.get(id);
  };

  function fit() {
    const vw = viewport.clientWidth, vh = viewport.clientHeight;
    const k = Math.min(vw / W, vh / H);
    stage.style.transform = `translate(${(vw - W * k) / 2}px, ${(vh - H * k) / 2}px) scale(${k})`;
  }
  addEventListener("resize", fit);
  fit();

  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let idx = -1, current = null, busy = false, timers = [];

  function builds(slide) {
    timers.forEach(clearTimeout);
    timers = [];
    const els = [...slide.querySelectorAll("[data-build-in]")].map((el) => {
      const [type = "fade", ord = "1"] = el.getAttribute("data-build-in").trim().split(/\s+/);
      el.classList.add("bi", "bi-" + type);
      return { el, ord: parseInt(ord, 10) || 1 };
    });
    if (reduce) return els.forEach((b) => b.el.classList.add("in"));
    const steps = [...new Set(els.map((b) => b.ord))].sort((a, b) => a - b);
    void slide.offsetWidth; // зафиксировать начальное состояние перед анимацией
    steps.forEach((ord, i) => {
      timers.push(setTimeout(() => els.filter((b) => b.ord === ord).forEach((b) => b.el.classList.add("in")), 350 + i * 260));
    });
  }

  async function show(i, dir = 1) {
    i = Math.max(0, Math.min(order.length - 1, i));
    if (i === idx || busy) return;
    busy = true;
    const html = await load(order[i]);
    const next = document.createElement("div");
    next.className = "slide";
    next.innerHTML = html;
    const section = next.querySelector("section");
    const kind = !reduce && current ? ((current.querySelector("section")?.dataset.transition === "push") ? "push" : "fade") : null;
    if (kind) next.classList.add("enter-" + kind);
    if (kind === "push" && dir < 0) next.style.translate = "-100% 0";
    stage.appendChild(next);
    builds(next);
    const prev = current;
    current = next;
    idx = i;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      next.classList.remove("enter-fade", "enter-push");
      next.style.translate = "";
      if (prev) prev.classList.add(kind === "push" ? "leave-push" : "leave-fade");
    }));
    setTimeout(() => { prev?.remove(); busy = false; }, prev ? 620 : 0);
    count.textContent = `${i + 1} / ${order.length}`;
    progress.style.width = `${((i + 1) / order.length) * 100}%`;
    history.replaceState(null, "", "#" + (i + 1));
    if (section) section.setAttribute("aria-label", `Слайд ${i + 1}`);
    load(order[i + 1] || order[i]); // подгрузить следующий заранее
  }

  const go = (d) => show(idx + d, d);
  addEventListener("keydown", (e) => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    const k = e.key;
    if (["ArrowRight", "ArrowDown", "PageDown", " ", "Enter"].includes(k)) { e.preventDefault(); go(1); }
    else if (["ArrowLeft", "ArrowUp", "PageUp", "Backspace"].includes(k)) { e.preventDefault(); go(-1); }
    else if (k === "Home") show(0, -1);
    else if (k === "End") show(order.length - 1, 1);
    else if (k === "f" || k === "F" || k === "а" || k === "А") toggleFull();
    wake();
  });
  viewport.addEventListener("click", (e) => go(e.clientX > innerWidth / 3 ? 1 : -1));
  let tx = null;
  viewport.addEventListener("touchstart", (e) => { tx = e.touches[0].clientX; }, { passive: true });
  viewport.addEventListener("touchend", (e) => {
    if (tx === null) return;
    const dx = e.changedTouches[0].clientX - tx;
    if (Math.abs(dx) > 40) go(dx < 0 ? 1 : -1);
    tx = null;
  });
  addEventListener("hashchange", () => {
    const n = parseInt(location.hash.slice(1), 10);
    if (n) show(n - 1, n - 1 > idx ? 1 : -1);
  });

  function toggleFull() {
    if (document.fullscreenElement) document.exitFullscreen?.();
    else document.documentElement.requestFullscreen?.().catch(() => {});
  }
  document.getElementById("prev").onclick = (e) => { e.stopPropagation(); go(-1); };
  document.getElementById("next").onclick = (e) => { e.stopPropagation(); go(1); };
  document.getElementById("full").onclick = (e) => { e.stopPropagation(); toggleFull(); };

  let hideT;
  function wake() {
    bar.classList.remove("hide");
    clearTimeout(hideT);
    hideT = setTimeout(() => bar.classList.add("hide"), 2600);
  }
  addEventListener("mousemove", wake);
  wake();
  setTimeout(() => { const h = document.getElementById("hint"); if (h) h.style.opacity = "0"; }, 4000);

  const start = parseInt(location.hash.slice(1), 10);
  show(start ? start - 1 : 0);
})();
