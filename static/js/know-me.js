/**
 * know-me.js — MemoryWall client logic
 * Signature canvas (mouse + touch + stylus), form submission, sharing, GA4 tracking
 */

(function () {
  'use strict';

  // ── Signature Canvas ─────────────────────────────────────────────────────
  const canvas = document.getElementById('km-sig-canvas');
  const hint   = document.querySelector('.km-sig-hint');
  let drawing  = false;
  let hasMark  = false;

  if (canvas) {
    const ctx = canvas.getContext('2d');
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth   = 2.5;
    ctx.lineCap     = 'round';
    ctx.lineJoin    = 'round';

    // Scale for device pixel ratio (retina)
    function resizeCanvas() {
      const rect = canvas.getBoundingClientRect();
      canvas.width  = rect.width  * window.devicePixelRatio;
      canvas.height = rect.height * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
      ctx.strokeStyle = '#1e293b';
      ctx.lineWidth   = 2.5;
      ctx.lineCap     = 'round';
      ctx.lineJoin    = 'round';
    }
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    function getPos(e) {
      const rect = canvas.getBoundingClientRect();
      const src  = e.touches ? e.touches[0] : e;
      return {
        x: (src.clientX - rect.left),
        y: (src.clientY - rect.top),
      };
    }

    function startDraw(e) {
      e.preventDefault();
      drawing = true;
      hasMark = true;
      if (hint) hint.classList.add('hidden');
      const { x, y } = getPos(e);
      ctx.beginPath();
      ctx.moveTo(x, y);
    }
    function draw(e) {
      if (!drawing) return;
      e.preventDefault();
      const { x, y } = getPos(e);
      ctx.lineTo(x, y);
      ctx.stroke();
    }
    function endDraw() { drawing = false; }

    canvas.addEventListener('mousedown',  startDraw);
    canvas.addEventListener('mousemove',  draw);
    canvas.addEventListener('mouseup',    endDraw);
    canvas.addEventListener('mouseleave', endDraw);
    canvas.addEventListener('touchstart', startDraw, { passive: false });
    canvas.addEventListener('touchmove',  draw,      { passive: false });
    canvas.addEventListener('touchend',   endDraw);
  }

  // Clear button
  const clearBtn = document.getElementById('km-sig-clear');
  if (clearBtn && canvas) {
    clearBtn.addEventListener('click', function () {
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      hasMark = false;
      if (hint) hint.classList.remove('hidden');
    });
  }

  // ── Emoji Picker ─────────────────────────────────────────────────────────
  let selectedEmoji = '';
  document.querySelectorAll('.km-emoji-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.km-emoji-btn').forEach(b => b.classList.remove('selected'));
      if (selectedEmoji === btn.dataset.emoji) {
        selectedEmoji = '';
      } else {
        btn.classList.add('selected');
        selectedEmoji = btn.dataset.emoji;
      }
    });
  });

  // ── Anonymous Toggle ──────────────────────────────────────────────────────
  let isAnonymous = false;
  const toggleRow    = document.getElementById('km-anon-toggle');
  const toggleSwitch = document.getElementById('km-anon-switch');
  if (toggleRow) {
    toggleRow.addEventListener('click', function () {
      isAnonymous = !isAnonymous;
      toggleSwitch.classList.toggle('on', isAnonymous);
      const label = document.getElementById('km-anon-label');
      if (label) label.textContent = isAnonymous ? 'Posting anonymously' : 'Include my name';
    });
  }

  // ── Form Submission ───────────────────────────────────────────────────────
  const form = document.getElementById('km-submit-form');
  if (form) {
    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      const btn = document.getElementById('km-submit-btn');
      const err = document.getElementById('km-form-error');
      if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
      if (err) err.style.display = 'none';

      const wallId   = form.dataset.wallId;
      const w1 = document.getElementById('km-word1').value.trim();
      const w2 = document.getElementById('km-word2').value.trim();
      const w3 = document.getElementById('km-word3').value.trim();
      const name = document.getElementById('km-name').value.trim();
      const mem  = document.getElementById('km-memory') ? document.getElementById('km-memory').value.trim() : '';
      const honey = document.getElementById('km-honey') ? document.getElementById('km-honey').value : '';

      if (!w1 || !w2 || !w3) {
        showError('Please enter all 3 words.');
        if (btn) { btn.disabled = false; btn.textContent = 'Send to MemoryWall ✨'; }
        return;
      }
      if (!name && !isAnonymous) {
        showError('Please enter your name, or post anonymously.');
        if (btn) { btn.disabled = false; btn.textContent = 'Send to MemoryWall ✨'; }
        return;
      }

      // Upload signature first if drawn
      let signatureUrl = '';
      if (hasMark && canvas) {
        try {
          const blob = await new Promise(res => canvas.toBlob(res, 'image/png'));
          if (blob && blob.size < 512 * 1024) {
            const fd = new FormData();
            fd.append('signature', blob, 'signature.png');
            const sigRes = await fetch('/api/memorywall/upload-signature', { method: 'POST', body: fd });
            const sigJson = await sigRes.json();
            if (sigJson.success) signatureUrl = sigJson.url;
          }
        } catch (ex) {
          console.warn('[MemoryWall] Signature upload failed, continuing without:', ex);
        }
      }

      // Submit response
      const payload = {
        wall_id: wallId,
        friend_name: isAnonymous ? 'Anonymous' : name,
        word_1: w1, word_2: w2, word_3: w3,
        memory_message: mem,
        emoji: selectedEmoji,
        anonymous: isAnonymous,
        signature_url: signatureUrl,
        _honey: honey, // honeypot
      };

      try {
        const res = await fetch('/api/memorywall/submit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const json = await res.json();
        if (json.success) {
          showSuccess();
          trackEvent('memorywall_submit', { wall_id: wallId });
        } else if (res.status === 429) {
          showError('Too many submissions. Please try again later.');
        } else {
          showError(json.message || 'Something went wrong. Please try again.');
        }
      } catch (ex) {
        showError('Network error. Please check your connection.');
      }

      if (btn) { btn.disabled = false; btn.textContent = 'Send to MemoryWall ✨'; }
    });
  }

  function showError(msg) {
    const err = document.getElementById('km-form-error');
    if (err) { err.textContent = msg; err.style.display = 'block'; }
  }

  function showSuccess() {
    const formCard = document.getElementById('km-form-card');
    const succCard = document.getElementById('km-success-card');
    if (formCard) formCard.style.display = 'none';
    if (succCard) succCard.style.display = 'block';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  // ── Share Buttons ─────────────────────────────────────────────────────────
  const copyBtn = document.getElementById('km-copy-link');
  if (copyBtn) {
    copyBtn.addEventListener('click', function () {
      const url = copyBtn.dataset.url || window.location.href;
      navigator.clipboard.writeText(url).then(function () {
        const orig = copyBtn.textContent;
        copyBtn.textContent = '✅ Copied!';
        setTimeout(() => { copyBtn.textContent = orig; }, 2000);
      });
      trackEvent('memorywall_share', { method: 'copy_link' });
    });
  }

  const waBtn = document.getElementById('km-wa-share');
  if (waBtn) {
    waBtn.addEventListener('click', function () {
      const url  = waBtn.dataset.url  || window.location.href;
      const text = waBtn.dataset.text || 'Check out my MemoryWall on AbhiHub!';
      window.open(`https://wa.me/?text=${encodeURIComponent(text + ' ' + url)}`, '_blank');
      trackEvent('memorywall_share', { method: 'whatsapp' });
    });
  }

  // ── Analytics helpers ─────────────────────────────────────────────────────
  function trackEvent(name, params) {
    if (typeof window.safeGtag === 'function') {
      window.safeGtag('event', name, Object.assign({ page_path: window.location.pathname }, params || {}));
    } else if (typeof gtag === 'function') {
      gtag('event', name, params || {});
    }
  }

  // Auto-track page views
  document.addEventListener('DOMContentLoaded', function () {
    const path = window.location.pathname;
    if (path === '/memorywall')               trackEvent('memorywall_view',     { view: 'dashboard' });
    else if (path === '/memorywall/create')   trackEvent('memorywall_create',   {});
    else if (path.startsWith('/m/'))          trackEvent('memorywall_view',     { view: 'public_wall', slug: path.split('/m/')[1] });
    else if (path.includes('/reveal/'))       trackEvent('memorywall_reveal',   {});
  });

})();
