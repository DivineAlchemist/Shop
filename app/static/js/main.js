document.addEventListener('DOMContentLoaded', () => {
  // Auto-dismiss flash messages
  document.querySelectorAll('.flashes .alert').forEach((el) => {
    setTimeout(() => {
      bootstrap.Alert.getOrCreateInstance(el).close();
    }, 4000);
  });

  // Auto-open search if there's a query in the URL
  const panel = document.getElementById('searchPanel');
  const input = panel?.querySelector('input[name="q"]');
  if (panel && input && input.value.trim() !== '') {
    new bootstrap.Collapse(panel, { toggle: true });
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }

  // Focus search input when panel opens
  panel?.addEventListener('shown.bs.collapse', () => input?.focus());

  const toggle = document.getElementById('themeToggle');
const root = document.documentElement;
const label = toggle?.querySelector('.theme-label');
const icon = toggle?.querySelector('i');

function applyTheme(theme) {
  root.setAttribute('data-bs-theme', theme);
  localStorage.setItem('theme', theme);
  if (label) label.textContent = theme === 'dark' ? 'Light mode' : 'Dark mode';
  if (icon) icon.className = theme === 'dark' ? 'bi bi-sun' : 'bi bi-moon-stars';
}

// Set initial label/icon on load
applyTheme(root.getAttribute('data-bs-theme') || 'light');

toggle?.addEventListener('click', () => {
  const next = root.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
  applyTheme(next);
});
});

// ---------- homepage product slider (horizontal, direction-aware, optional auto-scroll) ----------
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.hscroll').forEach((root) => {
    const track = root.querySelector('.hscroll__track');
    const items = [...track.querySelectorAll('.hscroll__item')];
    const dots = root.querySelectorAll('.hscroll__dots span');
    const rtl = () => getComputedStyle(track).direction === 'rtl';
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let idx = 0, timer = null, visible = true;
    const delta = (el) => {  // distance from the track's start edge, works for LTR and RTL
      const t = track.getBoundingClientRect(), r = el.getBoundingClientRect();
      return rtl() ? r.right - t.right : r.left - t.left;
    };
    const current = () => items.reduce((best, el, i) => (Math.abs(delta(el)) < Math.abs(delta(items[best])) ? i : best), 0);
    const go = (i) => {
      idx = (i + items.length) % items.length;
      track.scrollBy({ left: delta(items[idx]), behavior: reduced ? 'auto' : 'smooth' });  // never scrolls the page itself
    };
    const mark = () => { idx = current(); dots.forEach((d, n) => d.classList.toggle('active', n === idx)); };
    track.addEventListener('scroll', mark, { passive: true });
    mark();
    root.querySelector('[data-hs="prev"]')?.addEventListener('click', () => { go(current() - 1); restart(); });
    root.querySelector('[data-hs="next"]')?.addEventListener('click', () => { go(current() + 1); restart(); });
    track.addEventListener('keydown', (e) => {
      const fwd = rtl() ? 'ArrowLeft' : 'ArrowRight', back = rtl() ? 'ArrowRight' : 'ArrowLeft';
      if (e.key === fwd) { e.preventDefault(); go(current() + 1); }
      if (e.key === back) { e.preventDefault(); go(current() - 1); }
    });
    const auto = root.dataset.autoscroll === '1' && items.length > 1 && !reduced;
    const interval = Math.max(2000, parseInt(root.dataset.interval || '5000', 10));
    function stop() { clearInterval(timer); timer = null; }
    function start() { if (auto && visible && !timer) timer = setInterval(() => go(current() + 1), interval); }
    function restart() { stop(); start(); }
    ['mouseenter', 'focusin', 'touchstart'].forEach((ev) => root.addEventListener(ev, stop, { passive: true }));
    ['mouseleave', 'focusout', 'touchend'].forEach((ev) => root.addEventListener(ev, start, { passive: true }));
    document.addEventListener('visibilitychange', () => (document.hidden ? stop() : start()));
    if ('IntersectionObserver' in window) {  // only auto-advance while the slider is on screen
      new IntersectionObserver((es) => { visible = es[0].isIntersecting; visible ? start() : stop(); }).observe(root);
    }
    window.addEventListener('resize', () => go(idx));
    start();
  });

  // ---------- catalog filters: apply instantly on desktop, via "Show results" inside the mobile drawer ----------
  const form = document.getElementById('filterForm');
  if (form) {
    // category tree: ticking a child narrows (unticks its ancestors); ticking a parent replaces its children
    form.addEventListener('change', (e) => {
      const el = e.target;
      if (!el.classList || !el.classList.contains('cat-check') || !el.checked) return;
      form.querySelectorAll('.cat-check').forEach((o) => {
        if (o === el || !o.checked) return;
        if (el.dataset.path.startsWith(o.dataset.path) || o.dataset.path.startsWith(el.dataset.path)) o.checked = false;
      });
    }, true);
    let t;
    form.addEventListener('change', () => {
      if (window.matchMedia('(min-width: 992px)').matches) { clearTimeout(t); t = setTimeout(() => form.submit(), 250); }
    });
    form.querySelectorAll('[data-toggle-more]').forEach((btn) => btn.addEventListener('click', () => {
      const list = btn.closest('.filter-list');
      list.classList.toggle('show-all');
      btn.textContent = list.classList.contains('show-all') ? 'Show less' : 'Show more';
    }));
  }
});
