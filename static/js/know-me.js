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
      if (!name) {
        showError('Please enter your name.');
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
        friend_name: name,
        word_1: w1, word_2: w2, word_3: w3,
        memory_message: mem,
        emoji: selectedEmoji,
        anonymous: false,
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

  // ── Instagram Story Card (1080x1920) — Upgraded Generator ──────────────
  const downloadCardBtn = document.getElementById('km-download-card');
  if (downloadCardBtn) {
    downloadCardBtn.addEventListener('click', async function () {
      const btn   = downloadCardBtn;
      const name  = btn.dataset.name  || 'My';
      const count = parseInt(btn.dataset.count  || '0', 10);
      const trait = btn.dataset.trait || '';
      const tcount= parseInt(btn.dataset.traitcount || '0', 10);
      const w1    = btn.dataset.w1 || '';
      const w2    = btn.dataset.w2 || '';
      const w3    = btn.dataset.w3 || '';
      const url   = (btn.dataset.url || 'abhihub.run.place').replace(/https?:\/\//, '');

      const orig = btn.textContent;
      btn.disabled = true;
      btn.textContent = 'Generating…';

      const c   = document.createElement('canvas');
      c.width   = 1080;
      c.height  = 1920;
      const ctx = c.getContext('2d');

      // ── Background gradient ──────────────────────────────────────────
      const bg = ctx.createLinearGradient(0, 0, 1080, 1920);
      bg.addColorStop(0,   '#0f1117');
      bg.addColorStop(0.5, '#1a1f2e');
      bg.addColorStop(1,   '#0f1117');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, 1080, 1920);

      // ── Soft accent orb (top-left) ──────────────────────────────────
      const orb1 = ctx.createRadialGradient(150, 300, 0, 150, 300, 400);
      orb1.addColorStop(0,   'rgba(98,238,168,0.22)');
      orb1.addColorStop(1,   'rgba(98,238,168,0)');
      ctx.fillStyle = orb1;
      ctx.fillRect(0, 0, 1080, 700);

      // ── Soft accent orb (bottom-right) ─────────────────────────────
      const orb2 = ctx.createRadialGradient(950, 1700, 0, 950, 1700, 500);
      orb2.addColorStop(0,   'rgba(255,231,105,0.18)');
      orb2.addColorStop(1,   'rgba(255,231,105,0)');
      ctx.fillStyle = orb2;
      ctx.fillRect(0, 1200, 1080, 720);

      // ── Helpers ──────────────────────────────────────────────────────
      function pill(text, cx, cy, w, h, bg, fg, fs) {
        ctx.save();
        ctx.shadowColor = 'rgba(0,0,0,0.25)';
        ctx.shadowBlur  = 24;
        ctx.shadowOffsetY = 6;
        drawRoundRect(ctx, cx - w/2, cy - h/2, w, h, h/2, bg);
        ctx.restore();
        ctx.fillStyle   = fg;
        ctx.font        = `800 ${fs}px Kanit, sans-serif`;
        ctx.textAlign   = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(text, cx, cy);
      }

      // ── Brand header ─────────────────────────────────────────────────
      ctx.textAlign   = 'center';
      ctx.textBaseline = 'middle';
      ctx.font        = '900 42px Kanit, sans-serif';
      ctx.fillStyle   = '#62EEA8';
      ctx.fillText('AbhiHub', 540, 110);
      ctx.font        = '600 22px Kanit, sans-serif';
      ctx.fillStyle   = 'rgba(255,255,255,0.35)';
      ctx.fillText('M E M O R Y W A L L', 540, 158);

      // ── Profile initial circle ────────────────────────────────────────
      const initials = name.trim().split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();
      const circleGrad = ctx.createLinearGradient(440, 260, 640, 460);
      circleGrad.addColorStop(0, '#FFE769');
      circleGrad.addColorStop(1, '#62EEA8');
      ctx.beginPath();
      ctx.arc(540, 360, 90, 0, Math.PI*2);
      ctx.fillStyle = circleGrad;
      ctx.fill();
      ctx.font = '900 68px Kanit, sans-serif';
      ctx.fillStyle = '#1a202c';
      ctx.fillText(initials, 540, 362);

      // ── Name ─────────────────────────────────────────────────────────
      ctx.font        = '800 72px Kanit, sans-serif';
      ctx.fillStyle   = '#ffffff';
      ctx.fillText(name, 540, 510);

      // ── Emotional memory story line ──────────────────────────────────
      ctx.font        = '500 32px Kanit, sans-serif';
      ctx.fillStyle   = 'rgba(255,255,255,0.55)';
      const storyLine = count === 1
        ? `1 person took time to leave something behind for you ❤️`
        : `${count} people took time to leave something behind for you ❤️`;
      // Wrap if long
      wrapText(ctx, storyLine, 540, 590, 860, 44);

      // ── Most Loved Trait ─────────────────────────────────────────────
      if (trait) {
        ctx.font      = '600 24px Kanit, sans-serif';
        ctx.fillStyle = 'rgba(255,255,255,0.4)';
        ctx.fillText('THE TRAIT PEOPLE NOTICED MOST', 540, 720);

        // Glowing pill
        ctx.save();
        ctx.shadowColor = 'rgba(98,238,168,0.5)';
        ctx.shadowBlur  = 40;
        pill(trait.toUpperCase() + ' 💚', 540, 820, 640, 110, 'rgba(98,238,168,0.15)', '#62EEA8', 56);
        ctx.restore();

        if (tcount > 0) {
          ctx.font      = '500 26px Kanit, sans-serif';
          ctx.fillStyle = 'rgba(255,255,255,0.45)';
          ctx.fillText(`${tcount} people independently chose this word`, 540, 900);
        }
      }

      // ── Top 3 Words ──────────────────────────────────────────────────
      const words = [w1, w2, w3].filter(w => w.trim() !== '');
      if (words.length) {
        ctx.font      = '600 24px Kanit, sans-serif';
        ctx.fillStyle = 'rgba(255,255,255,0.35)';
        ctx.fillText('ALSO DESCRIBED AS', 540, trait ? 990 : 750);
        const startY  = trait ? 1060 : 820;
        const pillColors = [
          ['rgba(255,255,255,0.1)', 'rgba(255,255,255,0.9)'],
          ['rgba(255,231,105,0.12)', '#FFE769'],
          ['rgba(255,228,186,0.12)', '#FFE4BA'],
        ];
        words.forEach((word, i) => {
          const [bg2, fg2] = pillColors[i] || pillColors[0];
          pill(word.toUpperCase(), 540, startY + i * 140, 560, 96, bg2, fg2, 42);
        });
      }

      // ── Stats row ────────────────────────────────────────────────────
      const statsY = 1600;
      ctx.fillStyle = 'rgba(255,255,255,0.06)';
      roundedRect(ctx, 80, statsY, 920, 110, 24);
      const statItems = [
        ['❤️', count + ' Memories'],
        ['🌐', url],
      ];
      statItems.forEach((item, i) => {
        const x = 230 + i * 480;
        ctx.font      = '700 30px Kanit, sans-serif';
        ctx.fillStyle = '#ffffff';
        ctx.fillText(item[0] + ' ' + item[1], x, statsY + 55);
      });

      // ── Footer ───────────────────────────────────────────────────────
      ctx.font      = '600 24px Kanit, sans-serif';
      ctx.fillStyle = 'rgba(255,255,255,0.3)';
      ctx.fillText('Sign the wall at ' + url, 540, 1780);
      ctx.font      = '500 20px Kanit, sans-serif';
      ctx.fillStyle = 'rgba(255,255,255,0.18)';
      ctx.fillText(new Date().toLocaleDateString('en-IN', { month: 'long', year: 'numeric' }), 540, 1830);

      // ── Download ─────────────────────────────────────────────────────
      const link = document.createElement('a');
      link.download = `${name.toLowerCase().replace(/\s+/g,'_')}_memorywall_story.png`;
      link.href = c.toDataURL('image/png');
      link.click();

      btn.disabled = false;
      btn.textContent = orig;
      trackEvent('memorywall_story_download', { name });
    });
  }

  function wrapText(ctx, text, x, y, maxW, lineH) {
    const words = text.split(' ');
    let line = '';
    let lineY = y;
    words.forEach((word, i) => {
      const test = line + word + ' ';
      if (ctx.measureText(test).width > maxW && i > 0) {
        ctx.fillText(line.trim(), x, lineY);
        line  = word + ' ';
        lineY += lineH;
      } else {
        line = test;
      }
    });
    ctx.fillText(line.trim(), x, lineY);
  }

  function roundedRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x+r, y);
    ctx.lineTo(x+w-r, y);
    ctx.arcTo(x+w, y, x+w, y+r, r);
    ctx.lineTo(x+w, y+h-r);
    ctx.arcTo(x+w, y+h, x+w-r, y+h, r);
    ctx.lineTo(x+r, y+h);
    ctx.arcTo(x, y+h, x, y+h-r, r);
    ctx.lineTo(x, y+r);
    ctx.arcTo(x, y, x+r, y, r);
    ctx.closePath();
    ctx.fill();
  }

  // ── First Reveal Celebration (once per session) ──────────────────────────
  const celebModal = document.getElementById('km-celebrate-modal');
  const celebClose = document.getElementById('km-celebrate-close');
  const celebProgress = document.querySelector('.km-celebrate-progress');
  if (celebModal) {
    const KEY = 'km_revealed_' + (window.location.pathname);
    if (!sessionStorage.getItem(KEY)) {
      sessionStorage.setItem(KEY, '1');
      celebModal.style.display = 'flex';
      document.body.style.overflow = 'hidden';
      // Start progress bar
      requestAnimationFrame(() => {
        if (celebProgress) celebProgress.style.width = '100%';
      });
      // Auto-close after 3s
      const autoClose = setTimeout(closeCelebration, 3200);
      function closeCelebration() {
        clearTimeout(autoClose);
        celebModal.style.opacity = '0';
        celebModal.style.transition = 'opacity 0.3s';
        setTimeout(() => {
          celebModal.style.display = 'none';
          document.body.style.overflow = '';
        }, 320);
      }
      if (celebClose) celebClose.addEventListener('click', closeCelebration);
      celebModal.addEventListener('click', e => {
        if (e.target === celebModal) closeCelebration();
      });
    }
  }

  // ── Signature Card → Modal ───────────────────────────────────────────────
  const sigModal      = document.getElementById('km-sig-modal');
  const sigModalImg   = document.getElementById('km-sig-modal-img');
  const sigModalName  = document.getElementById('km-sig-modal-name');
  const sigModalTime  = document.getElementById('km-sig-modal-time');
  const sigModalAvatar= document.getElementById('km-sig-modal-avatar');
  const sigModalClose = document.getElementById('km-sig-modal-close');

  if (sigModal) {
    document.querySelectorAll('.km-sigcard').forEach(card => {
      card.addEventListener('click', e => {
        // Don't open if clicking reaction btn
        if (e.target.closest('.km-reaction-btn')) return;
        const img  = card.querySelector('.km-sigcard-img');
        const name = card.dataset.name || 'Anonymous';
        const iso  = card.dataset.date || '';
        if (!img) return;

        sigModalImg.src = img.src;
        sigModalName.textContent = name;
        sigModalAvatar.textContent = name[0].toUpperCase();
        sigModalTime.textContent = '🕒 ' + (relTime(iso) || iso.split('T')[0] || '—');

        sigModal.style.display = 'flex';
        sigModal.style.opacity = '1';
        sigModal.style.transition = '';
        document.body.style.overflow = 'hidden';
      });
    });

    function closeSigModal() {
      sigModal.style.opacity = '0';
      sigModal.style.transition = 'opacity 0.25s';
      setTimeout(() => {
        sigModal.style.display = 'none';
        document.body.style.overflow = '';
      }, 260);
    }
    if (sigModalClose) sigModalClose.addEventListener('click', closeSigModal);
    sigModal.addEventListener('click', e => {
      if (e.target === sigModal) closeSigModal();
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') { closeSigModal(); }
    });
  }

  // ── Most Loved Trait Share Button ────────────────────────────────────────
  const shareTraitBtn = document.getElementById('km-share-trait');
  if (shareTraitBtn) {
    shareTraitBtn.addEventListener('click', () => {
      const text = shareTraitBtn.dataset.text || '';
      const url  = shareTraitBtn.dataset.url  || window.location.href;
      const full = text + '\n\n' + url;
      if (navigator.share) {
        navigator.share({ text, url }).catch(() => {});
      } else {
        const wa = 'https://wa.me/?text=' + encodeURIComponent(full);
        window.open(wa, '_blank');
      }
    });
  }

  // ── Signature Wall: counter + scroll-reveal + sort ───────────────────────

  // Animated counter
  const sigCounter = document.getElementById('km-sig-count');
  if (sigCounter) {
    const target = parseInt(sigCounter.dataset.target || '0', 10);
    const duration = 1200;
    const step = Math.max(1, Math.floor(target / 60));
    let current = 0;
    const timer = setInterval(() => {
      current = Math.min(current + step, target);
      sigCounter.textContent = current;
      if (current >= target) clearInterval(timer);
    }, duration / (target / step || 1));
  }

  // Scroll-reveal for .km-sr elements
  if ('IntersectionObserver' in window) {
    const srObs = new IntersectionObserver((entries) => {
      entries.forEach((entry, i) => {
        if (entry.isIntersecting) {
          // Stagger by index within visible batch
          setTimeout(() => {
            entry.target.classList.add('km-sr--visible');
          }, (entry.target.dataset.srIdx || 0) * 60);
          srObs.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

    document.querySelectorAll('.km-sr').forEach((el, i) => {
      el.dataset.srIdx = i;
      srObs.observe(el);
    });
  } else {
    // Fallback: show all immediately
    document.querySelectorAll('.km-sr').forEach(el => el.classList.add('km-sr--visible'));
  }

  // Client-side sort (newest / oldest)
  const sortBtns = document.querySelectorAll('.km-sort-btn');
  const sigGrid  = document.getElementById('km-sigwall-grid');
  if (sortBtns.length && sigGrid) {
    sortBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        sortBtns.forEach(b => b.classList.remove('km-sort-btn--active'));
        btn.classList.add('km-sort-btn--active');

        const order = btn.dataset.sort;
        const items = Array.from(sigGrid.querySelectorAll('.km-sigcard'));

        items.sort((a, b) => {
          const da = a.dataset.date || '';
          const db = b.dataset.date || '';
          return order === 'newest' ? db.localeCompare(da) : da.localeCompare(db);
        });

        items.forEach(item => {
          item.classList.remove('km-sr--visible');
          sigGrid.appendChild(item);
        });
        items.forEach((item, i) => {
          setTimeout(() => item.classList.add('km-sr--visible'), i * 40);
        });
      });
    });
  }

  // Relative time for .km-sigcard-time elements
  function relTime(iso) {
    if (!iso) return null;
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    const h = Math.floor(m / 60);
    const d = Math.floor(h / 24);
    if (m < 1)  return 'Just now';
    if (m < 60) return `${m} min ago`;
    if (h < 24) return `${h}h ago`;
    if (d < 7)  return `${d}d ago`;
    return new Date(iso).toLocaleDateString('en-IN', { day:'numeric', month:'short' });
  }
  document.querySelectorAll('.km-sigcard-time').forEach(el => {
    const iso = el.dataset.iso;
    const rel = relTime(iso);
    if (rel) el.textContent = '\uD83D\uDD52 ' + rel;  // 🕒
  });

  // Reaction button toggle (local state only)
  document.querySelectorAll('.km-reaction-btn').forEach(btn => {
    btn.addEventListener('click', function () {
      const reacted = this.classList.toggle('km-reacted');
      // Micro bounce
      this.style.transform = 'scale(1.4)';
      setTimeout(() => { this.style.transform = ''; }, 200);
    });
  });

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
    if (path === '/memorywall')               trackEvent('memorywall_dashboard_view', { view: 'dashboard' });
    else if (path === '/memorywall/create')   trackEvent('memorywall_create',         {});
    else if (path.startsWith('/m/'))          trackEvent('memorywall_view',           { view: 'public_wall', slug: path.split('/m/')[1] });
    else if (path.includes('/reveal/'))       trackEvent('memorywall_reveal_view',    {});

    // Track signature wall view on reveal page
    if (path.includes('/reveal/')) {
      const sigWall = document.querySelector('.km-sig-masonry, .km-sw-img');
      if (sigWall && 'IntersectionObserver' in window) {
        const obs = new IntersectionObserver(entries => {
          if (entries[0].isIntersecting) {
            trackEvent('memorywall_signature_view', {});
            obs.disconnect();
          }
        }, { threshold: 0.3 });
        obs.observe(sigWall);
      }
    }

    // Track share button clicks
    document.querySelectorAll('#km-copy-link, #km-wa-share').forEach(btn => {
      btn.addEventListener('click', () => {
        trackEvent('memorywall_share_click', { method: btn.id === 'km-copy-link' ? 'copy' : 'whatsapp' });
      });
    });
  });

})();
