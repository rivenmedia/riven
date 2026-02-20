let rootElement = null;

function getRoot() {
  if (!rootElement) {
    rootElement = document.getElementById('toast-root');
  }
  return rootElement;
}

export function notify(message, tone = 'info', timeoutMs = 3200) {
  const root = getRoot();
  if (!root) {
    // fallback
    window.alert(message);
    return;
  }

  const toast = document.createElement('div');
  toast.className = `toast toast--${tone}`;
  toast.textContent = message;
  root.appendChild(toast);

  requestAnimationFrame(() => {
    toast.classList.add('is-visible');
  });

  window.setTimeout(() => {
    toast.classList.remove('is-visible');
    toast.classList.add('is-leaving');
    window.setTimeout(() => toast.remove(), 220);
  }, timeoutMs);
}
