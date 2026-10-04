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
});