/**
 * know-me.js — MemoryWall client logic
 * Signature canvas (mouse + touch + stylus), form submission, sharing, GA4 tracking, Instagram card generation
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
    ctx.strokeStyle = '#1a202c';
    ctx.lineWidth   = 3.0;
    ctx.lineCap     = 'round';
    ctx.lineJoin    = 'round';

    // Scale for device pixel ratio (retina)
    function resizeCanvas() {
      const rect = canvas.getBoundingClientRect();
      canvas.width  = rect.width  * window.devicePixelRatio;
      canvas.height = rect.height * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
      ctx.strokeStyle = '#1a202c';
      ctx.lineWidth   = 3.0;
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

  // ── Share Buttons & Link Copying ──────────────────────────────────────────
  const copyBtn = document.getElementById('km-copy-link');
  if (copyBtn) {
    copyBtn.addEventListener('click', function () {
      const url = copyBtn.dataset.url || window.location.href;
      navigator.clipboard.writeText(url).then(function () {
        const orig = copyBtn.textContent;
        copyBtn.textContent = '✅ Copied Link!';
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

  // Helper to draw rounded rectangles on canvas
  function drawRoundRect(ctx, x, y, width, height, radius, fillStyle) {
    ctx.fillStyle = fillStyle;
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + width - radius, y);
    ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
    ctx.lineTo(x + width, y + height - radius);
    ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    ctx.lineTo(x + radius, y + height);
    ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
    ctx.fill();
  }

  // ── Instagram Story Card (1080x1920) Client Generation ──────────────────
  const downloadCardBtn = document.getElementById('km-download-card');
  if (downloadCardBtn) {
    downloadCardBtn.addEventListener('click', function () {
      const name = downloadCardBtn.dataset.name || 'My';
      const count = downloadCardBtn.dataset.count || '0';
      const w1 = downloadCardBtn.dataset.w1 || '';
      const w2 = downloadCardBtn.dataset.w2 || '';
      const w3 = downloadCardBtn.dataset.w3 || '';
      const url = downloadCardBtn.dataset.url || 'abhibhub.com';

      // Create a canvas element
      const c = document.createElement('canvas');
      c.width = 1080;
      c.height = 1920;
      const ctx = c.getContext('2d');

      // 1. Draw gradient background
      const grad = ctx.createLinearGradient(0, 0, 0, 1920);
      grad.addColorStop(0, '#FFE769');
      grad.addColorStop(1, '#62EEA8');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, 1080, 1920);

      // 2. Draw brand header
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = '#1a202c';
      ctx.font = '900 48px Kanit, sans-serif';
      ctx.fillText('AbhiHub', 540, 140);
      ctx.font = '500 24px Kanit, sans-serif';
      ctx.fillStyle = '#4a5568';
      ctx.fillText('MEMORYWALL', 540, 195);

      // Draw subtle horizontal division line
      ctx.fillStyle = 'rgba(26, 32, 44, 0.1)';
      ctx.fillRect(440, 230, 200, 4);

      // 3. Draw User Title
      ctx.fillStyle = '#1a202c';
      ctx.font = '800 76px Kanit, sans-serif';
      ctx.fillText(name + "'s", 540, 430);
      ctx.font = '300 64px Kanit, sans-serif';
      ctx.fillText('MemoryWall', 540, 520);

      // 4. Draw words section title
      ctx.font = 'bold 28px Kanit, sans-serif';
      ctx.fillStyle = '#4a5568';
      ctx.fillText('DESCRIBED AS', 540, 700);

      // 5. Draw the 3 word capsules
      const words = [w1, w2, w3].filter(w => w.trim() !== '');
      let startY = 780;
      words.forEach((word, idx) => {
        const pillWidth = 560;
        const pillHeight = 110;
        const pillX = 540 - (pillWidth / 2);
        const pillY = startY + (idx * 150);

        // Pill shadow
        ctx.shadowColor = 'rgba(0, 0, 0, 0.08)';
        ctx.shadowBlur = 24;
        ctx.shadowOffsetY = 8;

        drawRoundRect(ctx, pillX, pillY, pillWidth, pillHeight, 55, '#ffffff');

        // Reset shadow for text
        ctx.shadowColor = 'transparent';
        ctx.shadowBlur = 0;
        ctx.shadowOffsetY = 0;

        // Draw text
        ctx.fillStyle = '#1a202c';
        ctx.font = '800 44px Kanit, sans-serif';
        ctx.fillText(word.toUpperCase(), 540, pillY + 55);
      });

      // 6. Draw statistics
      ctx.fillStyle = '#4a5568';
      ctx.font = 'bold 36px Kanit, sans-serif';
      ctx.fillText(count + ' memories shared', 540, 1420);

      // 7. Draw date
      const dateStr = new Date().toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
      ctx.font = '500 28px Kanit, sans-serif';
      ctx.fillStyle = '#718096';
      ctx.fillText(dateStr, 540, 1480);

      // 8. Draw Link box
      const linkBoxY = 1630;
      ctx.shadowColor = 'rgba(0, 0, 0, 0.04)';
      ctx.shadowBlur = 16;
      drawRoundRect(ctx, 540 - 350, linkBoxY, 700, 100, 50, 'rgba(255, 255, 255, 0.8)');
      ctx.shadowColor = 'transparent';

      ctx.fillStyle = '#1a202c';
      ctx.font = 'bold 32px Kanit, sans-serif';
      ctx.fillText(url.replace('https://', '').replace('http://', ''), 540, linkBoxY + 50);

      // 9. Download trigger
      const link = document.createElement('a');
      link.download = `${name.toLowerCase().replace(/\s+/g, '_')}_memorywall.png`;
      link.href = c.toDataURL('image/png');
      link.click();
      trackEvent('memorywall_share', { method: 'download_card' });
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
