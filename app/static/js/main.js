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