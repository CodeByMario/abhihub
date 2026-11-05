/**
 * static/js/admin-dashboard.js
 * Unified client-side utilities for AbhiHub Admin Command Center.
 * Handles XSS sanitation, CSRF headers, confirmation modals, and toast alerts.
 */

(function (window) {
  'use strict';

  // ── XSS Prevention Helper ──────────────────────────────────────────────
  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // ── CSRF Token Retrieval ───────────────────────────────────────────────
  function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    const input = document.querySelector('input[name="csrf_token"]');
    if (input && input.value) return input.value;
    // Cookie fallback
    const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  // ── Secure Fetch Wrapper ───────────────────────────────────────────────
  async function adminFetch(url, options = {}) {
    options.headers = options.headers || {};
    const method = (options.method || 'GET').toUpperCase();

    // Attach CSRF token on state-changing methods
    if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
      const token = getCsrfToken();
      if (token) {
        options.headers['X-CSRFToken'] = token;
        options.headers['X-CSRF-Token'] = token;
      }
      if (!options.headers['Content-Type'] && !(options.body instanceof FormData)) {
        options.headers['Content-Type'] = 'application/json';
      }
    }

    try {
      const response = await fetch(url, options);
      if (response.status === 401) {
        showAdminToast('Session expired. Redirecting to login...', 'error');
        setTimeout(() => { window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname); }, 1200);
        return { success: false, error: 'Unauthorized' };
      }
      if (response.status === 403) {
        const data = await response.json().catch(() => ({}));
        showAdminToast(data.message || 'Permission denied. Admin privileges required.', 'error');
        return { success: false, error: data.message || 'Forbidden' };
      }
      return response;
    } catch (err) {
      showAdminToast('Network error: ' + err.message, 'error');
      throw err;
    }
  }

  // ── Toast Notification System ──────────────────────────────────────────
  function showAdminToast(message, type = 'info') {
    let container = document.getElementById('adminToastContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'adminToastContainer';
      document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `admin-toast ${type}`;
    const icon = type === 'success' ? 'fa-check-circle' : (type === 'error' ? 'fa-triangle-exclamation' : 'fa-circle-info');
    toast.innerHTML = `<i class="fas ${icon}"></i> <span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.25s ease';
      setTimeout(() => toast.remove(), 250);
    }, 4500);
  }

  // ── Confirmation Modal ─────────────────────────────────────────────────
  function adminConfirm(message, title = 'Confirm Action', isDestructive = false) {
    return new Promise((resolve) => {
      const modal = document.createElement('div');
      modal.className = 'admin-modal-overlay';
      modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.65);backdrop-filter:blur(4px);z-index:10000;display:flex;align-items:center;justify-content:center;padding:1rem;';
      
      const confirmColor = isDestructive ? '#ef4444' : '#6366f1';
      modal.innerHTML = `
        <div style="background:var(--bg-card,#1e293b);border:1px solid var(--border-subtle,rgba(255,255,255,0.1));border-radius:14px;padding:1.5rem;max-width:440px;width:100%;box-shadow:0 20px 40px rgba(0,0,0,0.5);animation:slideIn 0.2s ease;">
          <h3 style="margin:0 0 0.5rem;font-size:1.15rem;color:var(--text-primary,#fff);display:flex;align-items:center;gap:0.5rem;">
            <i class="fas ${isDestructive ? 'fa-triangle-exclamation text-rose-500' : 'fa-circle-question text-indigo-400'}"></i>
            ${escapeHtml(title)}
          </h3>
          <p style="margin:0 0 1.25rem;color:var(--text-secondary,#94a3b8);font-size:0.9rem;line-height:1.45;">
            ${escapeHtml(message)}
          </p>
          <div style="display:flex;justify-content:flex-end;gap:0.75rem;">
            <button id="adminConfirmCancel" style="padding:0.5rem 1rem;background:transparent;border:1px solid var(--border-subtle,rgba(255,255,255,0.15));color:var(--text-secondary,#94a3b8);border-radius:8px;cursor:pointer;font-size:0.85rem;font-weight:600;">Cancel</button>
            <button id="adminConfirmOk" style="padding:0.5rem 1rem;background:${confirmColor};border:none;color:#fff;border-radius:8px;cursor:pointer;font-size:0.85rem;font-weight:700;">Confirm</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);

      modal.querySelector('#adminConfirmCancel').onclick = () => {
        modal.remove();
        resolve(false);
      };
      modal.querySelector('#adminConfirmOk').onclick = () => {
        modal.remove();
        resolve(true);
      };
    });
  }

  // Export to global scope
  window.adminEscapeHtml = escapeHtml;
  window.getCsrfToken = getCsrfToken;
  window.adminFetch = adminFetch;
  window.showAdminToast = showAdminToast;
  window.adminConfirm = adminConfirm;

})(window);
