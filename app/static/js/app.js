// ── API helper ────────────────────────────────────────────────────────────────
async function apiFetch(url, opts = {}) {
  const defaults = {
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
  };
  const res = await fetch(url, { ...defaults, ...opts, headers: { ...defaults.headers, ...(opts.headers||{}) } });

  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const err = await res.json();
      msg = err.detail || err.message || msg;
    } catch (_) {}
    throw new Error(msg);
  }
  return res.json();
}

// ── Toast notifications ───────────────────────────────────────────────────────
function showToast(message, type = '') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    toast.style.transition = 'opacity .25s, transform .25s';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ── Score badge ───────────────────────────────────────────────────────────────
function scoresBadge(score) {
  if (!score && score !== 0) return '<span class="badge badge-gray">—</span>';
  const s = parseFloat(score);
  const cls = s >= 75 ? 'badge-green' : s >= 50 ? 'badge-amber' : 'badge-red';
  return `<span class="badge ${cls}">${s.toFixed(1)}</span>`;
}

// ── Date formatter ────────────────────────────────────────────────────────────
function formatDate(isoStr) {
  if (!isoStr) return '—';
  const d = new Date(isoStr);
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}
