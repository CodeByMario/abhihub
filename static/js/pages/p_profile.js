/* extracted page scripts for p_profile.html */

/* Show 5 more per click */
function showMore(section) {
    const selectors = ['.' + section + '-file-card.hidden', '.' + section + '-item.hidden', '.' + section + '-card.hidden'];
    const hidden = document.querySelectorAll(selectors.join(', '));
    let revealed = 0;
    hidden.forEach(el => {
        if (revealed < 5) {
            el.classList.remove('hidden');
            revealed++;
        }
    });
    const remaining = document.querySelectorAll(selectors.join(', ')).length;
    const btn = document.getElementById(section + '-show-more');
    if (btn) {
        remaining === 0 ? (btn.style.display = 'none') : (btn.textContent = '↓ Show more (' + remaining + ' more)');
    }
}

// Global click delegation for data-action="showMore" buttons
document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action="showMore"]');
    if (btn) {
        const category = btn.getAttribute('data-category');
        if (category) {
            showMore(category);
        }
    }
});

/* Access level check */
(function () {
    fetch('/api/my-access')
        .then(r => r.json())
        .then(d => {
            if (!d.success || !d.progress) return;
            const wrap = document.getElementById('access-badge');
            if (!wrap) return;
            const names = {
                explorer: 'Explorer',
                member: 'Member',
                contributor: 'Contributor',
                power_contributor: 'Power Contributor',
                community_leader: 'Community Leader'
            };
            const lvlName = document.getElementById('access-level-name');
            const bar = document.getElementById('access-progress-bar');
            const next = document.getElementById('access-next');
            if (lvlName) lvlName.textContent = names[d.level] || d.level;
            if (bar) bar.style.width = Math.round((d.progress.progress || 0) * 100) + '%';
            if (next) {
                next.textContent = d.progress.next_level
                    ? names[d.progress.next_level] + ' @ ' + d.progress.next_threshold
                    : 'Max level 🎉';
            }
            wrap.style.display = 'flex';
        })
        .catch(() => { });
})();

/* Eligibility check */
(function () {
    const btn = document.getElementById('checkEligibilityBtn');
    const out = document.getElementById('eligibilityResult');
    if (!btn || !out) return;

    function render(eligible) {
        out.style.display = 'block';
        if (eligible) {
            out.innerHTML = '<div style="color:#059669;">✅ You are eligible — rewards are coming soon.</div>';
        } else {
            out.innerHTML = '<div style="color:#b45309;">❌ Not eligible yet — reach <strong>Contributor</strong> rank to unlock rewards.</div>';
        }
    }

    btn.addEventListener('click', async () => {
        out.style.display = 'none';
        btn.disabled = true;
        btn.textContent = 'Checking…';
        try {
            const r = await fetch('/api/my-access');
            const d = await r.json();
            if (!d.success) throw new Error('Failed to load access data');
            const level = (d.level || 'explorer').toLowerCase();
            const eligible = ['contributor', 'power_contributor', 'community_leader'].includes(level);
            render(eligible);
        } catch (e) {
            out.style.display = 'block';
            out.innerHTML = '<div style="color:#b45309;">Could not check eligibility right now.</div>';
        } finally {
            btn.disabled = false;
            btn.textContent = 'Check Eligibility';
        }
    });
})();

/* Notification toggle */
let _notifSubscribed = false;

async function initNotifToggle() {
    const track = document.getElementById('toggleTrack');
    const thumb = document.getElementById('toggleThumb');
    const status = document.getElementById('notifStatus');
    const btn = document.getElementById('notificationToggle');

    if (!window.PushNotifications?.isSupported()) {
        if (status) status.textContent = 'Not supported on this browser';
        if (btn) btn.style.opacity = '0.5';
        return;
    }

    const state = await PushNotifications.init();

    if (state.permission === 'denied') {
        _notifSubscribed = false;
        if (track) track.style.background = '#fca5a5';
        if (thumb) thumb.style.transform = 'translateX(18px)';
        if (status) status.textContent = 'Blocked — allow in browser settings';
        if (btn) btn.setAttribute('aria-checked', 'false');
    } else if (state.subscribed) {
        _notifSubscribed = true;
        if (track) track.style.background = '#10b981';
        if (thumb) thumb.style.transform = 'translateX(18px)';
        if (status) status.textContent = 'Enabled';
        if (btn) btn.setAttribute('aria-checked', 'true');
    } else {
        _notifSubscribed = false;
        if (track) track.style.background = '#d1d5db';
        if (thumb) thumb.style.transform = 'translateX(0)';
        if (status) status.textContent = 'Tap to enable';
        if (btn) btn.setAttribute('aria-checked', 'false');
    }
}

async function handleNotificationToggle() {
    const track = document.getElementById('toggleTrack');
    const thumb = document.getElementById('toggleThumb');
    const status = document.getElementById('notifStatus');
    const btn = document.getElementById('notificationToggle');

    if (!window.PushNotifications?.isSupported()) {
        if (status) status.textContent = 'Not supported on this browser';
        return;
    }

    const state = await PushNotifications.init();

    if (state.permission === 'denied') {
        if (status) status.textContent = 'Blocked — allow in browser settings';
        if (track) track.style.background = '#fca5a5';
        if (thumb) thumb.style.transform = 'translateX(18px)';
        return;
    }

    btn.disabled = true;
    if (status) status.textContent = state.subscribed ? 'Disabling…' : 'Enabling…';

    try {
        if (state.subscribed) {
            const result = await PushNotifications.unsubscribe();
            if (result.success) {
                _notifSubscribed = false;
                if (track) track.style.background = '#d1d5db';
                if (thumb) thumb.style.transform = 'translateX(0)';
                if (status) status.textContent = 'Disabled';
                btn.setAttribute('aria-checked', 'false');
                localStorage.removeItem('abhihub_notif_nudge_done');
            } else {
                if (status) status.textContent = 'Failed to disable — try again';
            }
        } else {
            const result = await PushNotifications.subscribe();
            if (result.success) {
                _notifSubscribed = true;
                if (track) track.style.background = '#10b981';
                if (thumb) thumb.style.transform = 'translateX(18px)';
                if (status) status.textContent = 'Enabled';
                btn.setAttribute('aria-checked', 'true');
                localStorage.setItem('abhihub_notif_nudge_done', '1');
            } else if (result.error === 'Permission denied') {
                if (track) track.style.background = '#fca5a5';
                if (thumb) thumb.style.transform = 'translateX(18px)';
                if (status) status.textContent = 'Blocked — allow in browser settings';
            } else {
                if (status) status.textContent = 'Failed — try again';
            }
        }
    } catch (e) {
        console.error('[NotifToggle]', e);
        if (status) status.textContent = 'Error — try again';
    } finally {
        btn.disabled = false;
    }
}

function checkVersionAndCache() {
    const currentVersion = '1.0.0';
    const cachedVersion = localStorage.getItem('abhihub_app_version');

    if (cachedVersion && cachedVersion !== currentVersion) {
        showUpdatePrompt(currentVersion);
    }

    localStorage.setItem('abhihub_app_version', currentVersion);
}

function showUpdatePrompt(currentVersion) {
    const overlay = document.createElement('div');
    overlay.style.position = 'fixed';
    overlay.style.top = '0';
    overlay.style.left = '0';
    overlay.style.width = '100%';
    overlay.style.height = '100%';
    overlay.style.background = 'rgba(0, 0, 0, 0.8)';
    overlay.style.zIndex = '9999';
    overlay.style.display = 'flex';
    overlay.style.alignItems = 'center';
    overlay.style.justifyContent = 'center';
    overlay.style.color = 'white';

    const card = document.createElement('div');
    card.style.background = '#1e1b4b';
    card.style.padding = '2rem 3rem';
    card.style.borderRadius = '12px';
    card.style.maxWidth = '90%';
    card.style.textAlign = 'center';

    card.innerHTML =
        '<div style="font-size: 4rem; margin-bottom: 1rem;">📱</div>' +
        '<h2>App Update Available</h2>' +
        '<p>Current version: <strong>' + (currentVersion || '1.0.0') + '</strong></p>' +
        '<p>A new version of AbhiHub is available. Please update to continue using all features.</p>' +
        '<div style="margin-top: 2rem; display: flex; gap: 1rem; justify-content: center;"><button id="btnUpdateNow" style="background: #3b82f6; color: white; border: none; padding: 0.8rem 1.5rem; border-radius: 8px; font-weight: 600; cursor: pointer;">Update Now</button>' +
        '<button id="btnDismiss" style="background: #6b7280; color: white; border: none; padding: 0.8rem 1.5rem; border-radius: 8px; font-weight: 600; cursor: pointer;">Later</button></div>';

    overlay.appendChild(card);
    document.body.appendChild(overlay);

    const updateBtn = document.getElementById('btnUpdateNow');
    const dismissBtn = document.getElementById('btnDismiss');
    if (updateBtn) {
        updateBtn.onclick = () => {
            window.open('https://abhihub.edu.eu.org/update', '_blank');
        };
    }
    if (dismissBtn) {
        dismissBtn.onclick = () => {
            document.body.removeChild(overlay);
        };
    }
}

function clearCacheAndRefresh() {
    localStorage.removeItem('abhihub_cache');
    localStorage.removeItem('abhihub_user_data');
    localStorage.removeItem('abhihub_rank');
    localStorage.removeItem('abhihub_reputation');
    localStorage.removeItem('abhihub_app_version');
    window.location.reload();
}

function updateServiceWorker() {
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.getRegistrations().then(registrations => {
            registrations.forEach(registration => {
                registration.unregister();
            });
        });
    }
    localStorage.removeItem('abhihub_app_version');
    localStorage.removeItem('abhihub_cache');
    localStorage.removeItem('abhihub_user_data');
    localStorage.removeItem('abhihub_rank');
    localStorage.removeItem('abhihub_reputation');
    showUpdatePrompt();
    window.location.reload();
}

document.addEventListener('DOMContentLoaded', () => {
    setTimeout(initNotifToggle, 400);
    checkVersionAndCache();
});
