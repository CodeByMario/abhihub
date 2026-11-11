/**
 * AbhiHub Gesture Navigation Controller (Apple & Android HIG)
 * - Swipe DOWN from top edge (<= 70px) -> Open Account / Notification Drawer
 * - Swipe UP to close Notification Drawer
 * - Swipe LEFT from right edge (>= W - 60px) -> Open Tarika AI Assistant
 * - Swipe RIGHT to close Tarika AI Assistant
 * - Swipe UP from bottom edge (>= H - 90px) -> Open Spotlight Search Sheet
 * - Swipe DOWN to close Spotlight Search Sheet
 * - 1:1 Interactive finger-tracking drag with spring physics & velocity fling
 * - Seamless bridge support across iframe content
 */
(function () {
  'use strict';

  var isTopWindow = (window.self === window.top);
  var startX = 0, startY = 0, startTime = 0;
  var currentX = 0, currentY = 0;
  var tracking = null;
  var isDragging = false;

  function getDrawerElements() {
    return {
      notif: document.getElementById('shellNotifPanel'),
      notifBackdrop: document.getElementById('shellNotifBackdrop'),
      tarika: document.getElementById('abhiAiDrawer'),
      tarikaBackdrop: document.getElementById('tarikaBackdrop'),
      search: document.getElementById('abhiSearchDrawer'),
      searchBackdrop: document.getElementById('searchDrawerBackdrop')
    };
  }

  function onTouchStart(e) {
    if (e.touches.length !== 1) return;
    var t = e.touches[0];
    startX = t.clientX;
    startY = t.clientY;
    currentX = startX;
    currentY = startY;
    startTime = Date.now();
    isDragging = false;
    tracking = null;

    var w = window.innerWidth;
    var h = window.innerHeight;

    var els = getDrawerElements();
    var notifOpen = (els.notif && els.notif.classList.contains('open'));
    var tarikaOpen = (els.tarika && els.tarika.classList.contains('active'));
    var searchOpen = (els.search && (els.search.classList.contains('open') || els.search.classList.contains('active')));

    // Drag to close already open drawer
    if (notifOpen && els.notif && els.notif.contains(e.target)) {
      tracking = 'NOTIF_CLOSE';
      return;
    }
    if (tarikaOpen && els.tarika && els.tarika.contains(e.target)) {
      tracking = 'TARIKA_CLOSE';
      return;
    }
    if (searchOpen && els.search && (e.target.closest('.sd-grab-bar') || e.target.closest('.sd-spotlight-header') || e.target.closest('#abhiSearchDrawer'))) {
      tracking = 'SEARCH_CLOSE';
      return;
    }

    // Only initiate open if no drawer is active
    if (!notifOpen && !tarikaOpen && !searchOpen) {
      if (startY <= 70) {
        tracking = 'NOTIF_DOWN';
      } else if (startX >= w - 65) {
        tracking = 'TARIKA_LEFT';
      } else if (startY >= h - 90) {
        tracking = 'SEARCH_UP';
      }
    }
  }

  function onTouchMove(e) {
    if (!tracking || e.touches.length !== 1) return;
    var t = e.touches[0];
    currentX = t.clientX;
    currentY = t.clientY;

    var diffX = currentX - startX;
    var diffY = currentY - startY;

    if (!isDragging) {
      if (tracking === 'NOTIF_DOWN' && diffY > 10 && Math.abs(diffY) > Math.abs(diffX)) {
        isDragging = true;
      } else if (tracking === 'TARIKA_LEFT' && diffX < -10 && Math.abs(diffX) > Math.abs(diffY)) {
        isDragging = true;
      } else if (tracking === 'SEARCH_UP' && diffY < -10 && Math.abs(diffY) > Math.abs(diffX)) {
        isDragging = true;
      } else if (tracking === 'NOTIF_CLOSE' && diffY < -10 && Math.abs(diffY) > Math.abs(diffX)) {
        isDragging = true;
      } else if (tracking === 'TARIKA_CLOSE' && diffX > 10 && Math.abs(diffX) > Math.abs(diffY)) {
        isDragging = true;
      } else if (tracking === 'SEARCH_CLOSE' && diffY > 10 && Math.abs(diffY) > Math.abs(diffX)) {
        isDragging = true;
      } else if (Math.abs(diffX) > 16 || Math.abs(diffY) > 16) {
        tracking = null;
        return;
      }
    }

    if (!isDragging) return;
    if (e.cancelable) e.preventDefault();

    if (!isTopWindow) return;

    var els = getDrawerElements();
    var h = window.innerHeight;

    if (tracking === 'NOTIF_DOWN' && els.notif) {
      var notifH = els.notif.offsetHeight || 380;
      var moveY = Math.min(0, -notifH + diffY);
      els.notif.style.transition = 'none';
      els.notif.style.visibility = 'visible';
      els.notif.style.transform = 'translateY(' + moveY + 'px)';
      if (els.notifBackdrop) {
        els.notifBackdrop.style.display = 'block';
        els.notifBackdrop.style.opacity = Math.min(1, diffY / 180).toFixed(2);
      }
    } else if (tracking === 'NOTIF_CLOSE' && els.notif) {
      var moveY = Math.min(0, diffY);
      els.notif.style.transition = 'none';
      els.notif.style.transform = 'translateY(' + moveY + 'px)';
    } else if (tracking === 'TARIKA_LEFT' && els.tarika) {
      var tarikaW = els.tarika.offsetWidth || 380;
      var moveX = Math.max(0, tarikaW + diffX);
      els.tarika.style.transition = 'none';
      els.tarika.style.transform = 'translateX(' + moveX + 'px)';
      if (els.tarikaBackdrop) {
        els.tarikaBackdrop.style.display = 'block';
        els.tarikaBackdrop.style.opacity = Math.min(1, Math.abs(diffX) / tarikaW).toFixed(2);
      }
    } else if (tracking === 'TARIKA_CLOSE' && els.tarika) {
      var moveX = Math.max(0, diffX);
      els.tarika.style.transition = 'none';
      els.tarika.style.transform = 'translateX(' + moveX + 'px)';
    } else if (tracking === 'SEARCH_UP' && els.search) {
      var searchH = els.search.offsetHeight || h;
      var moveY = Math.max(0, searchH + diffY);
      els.search.style.transition = 'none';
      els.search.style.visibility = 'visible';
      els.search.style.transform = 'translateY(' + moveY + 'px)';
      if (els.searchBackdrop) {
        els.searchBackdrop.style.display = 'block';
        els.searchBackdrop.style.opacity = Math.min(1, Math.abs(diffY) / 250).toFixed(2);
      }
    } else if (tracking === 'SEARCH_CLOSE' && els.search) {
      var moveY = Math.max(0, diffY);
      els.search.style.transition = 'none';
      els.search.style.transform = 'translateY(' + moveY + 'px)';
    }
  }

  function onTouchEnd() {
    if (!tracking || !isDragging) {
      tracking = null;
      isDragging = false;
      return;
    }

    var diffX = currentX - startX;
    var diffY = currentY - startY;
    var duration = Math.max(1, Date.now() - startTime);
    var velX = Math.abs(diffX) / duration;
    var velY = Math.abs(diffY) / duration;

    var THRESHOLD = 60;
    var VEL_THRESHOLD = 0.35;

    if (!isTopWindow) {
      if (tracking === 'NOTIF_DOWN' && (diffY > THRESHOLD || velY > VEL_THRESHOLD)) {
        try { window.parent.postMessage({ type: 'GESTURE_SWIPE', action: 'OPEN_NOTIF' }, '*'); } catch (e) {}
      } else if (tracking === 'NOTIF_CLOSE' && (-diffY > 40 || velY > VEL_THRESHOLD)) {
        try { window.parent.postMessage({ type: 'GESTURE_SWIPE', action: 'CLOSE_NOTIF' }, '*'); } catch (e) {}
      } else if (tracking === 'TARIKA_LEFT' && (-diffX > THRESHOLD || velX > VEL_THRESHOLD)) {
        try { window.parent.postMessage({ type: 'GESTURE_SWIPE', action: 'OPEN_TARIKA' }, '*'); } catch (e) {}
      } else if (tracking === 'TARIKA_CLOSE' && (diffX > 40 || velX > VEL_THRESHOLD)) {
        try { window.parent.postMessage({ type: 'GESTURE_SWIPE', action: 'CLOSE_TARIKA' }, '*'); } catch (e) {}
      } else if (tracking === 'SEARCH_UP' && (-diffY > THRESHOLD || velY > VEL_THRESHOLD)) {
        try { window.parent.postMessage({ type: 'GESTURE_SWIPE', action: 'OPEN_SEARCH' }, '*'); } catch (e) {}
      } else if (tracking === 'SEARCH_CLOSE' && (diffY > 40 || velY > VEL_THRESHOLD)) {
        try { window.parent.postMessage({ type: 'GESTURE_SWIPE', action: 'CLOSE_SEARCH' }, '*'); } catch (e) {}
      }
      tracking = null;
      isDragging = false;
      return;
    }

    var els = getDrawerElements();

    if (els.notif) { els.notif.style.transition = ''; els.notif.style.transform = ''; }
    if (els.notifBackdrop) { els.notifBackdrop.style.opacity = ''; }
    if (els.tarika) { els.tarika.style.transition = ''; els.tarika.style.transform = ''; }
    if (els.tarikaBackdrop) { els.tarikaBackdrop.style.opacity = ''; }
    if (els.search) { els.search.style.transition = ''; els.search.style.transform = ''; }
    if (els.searchBackdrop) { els.searchBackdrop.style.opacity = ''; }

    if (tracking === 'NOTIF_DOWN') {
      if (diffY > THRESHOLD || velY > VEL_THRESHOLD) {
        if (typeof window.openNotifPanel === 'function') window.openNotifPanel();
      } else {
        if (typeof window.closeNotifPanel === 'function') window.closeNotifPanel();
      }
    } else if (tracking === 'NOTIF_CLOSE') {
      if (-diffY > 40 || velY > VEL_THRESHOLD) {
        if (typeof window.closeNotifPanel === 'function') window.closeNotifPanel();
      }
    } else if (tracking === 'TARIKA_LEFT') {
      if (-diffX > THRESHOLD || velX > VEL_THRESHOLD) {
        if (typeof window.openTarikaDrawer === 'function') window.openTarikaDrawer();
      } else {
        if (typeof window.closeTarikaDrawer === 'function') window.closeTarikaDrawer();
      }
    } else if (tracking === 'TARIKA_CLOSE') {
      if (diffX > 40 || velX > VEL_THRESHOLD) {
        if (typeof window.closeTarikaDrawer === 'function') window.closeTarikaDrawer();
      }
    } else if (tracking === 'SEARCH_UP') {
      if (-diffY > THRESHOLD || velY > VEL_THRESHOLD) {
        if (typeof window.openSearchDrawer === 'function') window.openSearchDrawer();
      } else {
        if (typeof window.closeSearchDrawer === 'function') window.closeSearchDrawer();
      }
    } else if (tracking === 'SEARCH_CLOSE') {
      if (diffY > 40 || velY > VEL_THRESHOLD) {
        if (typeof window.closeSearchDrawer === 'function') window.closeSearchDrawer();
      }
    }

    tracking = null;
    isDragging = false;
  }

  document.addEventListener('touchstart', onTouchStart, { passive: true });
  document.addEventListener('touchmove', onTouchMove, { passive: false });
  document.addEventListener('touchend', onTouchEnd, { passive: true });
  document.addEventListener('touchcancel', onTouchEnd, { passive: true });
})();
