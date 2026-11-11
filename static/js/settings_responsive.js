/**
 * AbhiHub - Settings Responsive Controller (Mobile List-to-Detail & History Sync)
 * Compliant with Apple HIG & Material M3 standards.
 * Uses sticky Back button + history.pushState/popstate. No fragile edge-swipe handlers.
 */

(function() {
  'use strict';

  let hasUnsavedChanges = false;
  let activeFormEl = null;

  // 1. Mobile List-to-Detail Transitions with pushState
  function openMobileDetail(sectionId, shouldPushState = true) {
    if (window.innerWidth > 768) return;
    const container = document.querySelector('.st-container');
    if (container) {
      container.classList.add('mobile-detail-open');
    }
    const titleEl = document.getElementById('stMobileDetailTitle');
    if (titleEl) {
      const activeBtn = document.querySelector(`#settingsNav .st-nav-item[data-section="${sectionId}"] .st-nav-title`);
      if (activeBtn) {
        titleEl.textContent = activeBtn.textContent;
      }
    }

    if (shouldPushState && history.pushState) {
      try {
        const url = new URL(window.location.href);
        if (url.hash !== '#' + sectionId) {
          url.hash = sectionId;
          history.pushState({ section: sectionId, mobileDetail: true }, '', url.toString());
        }
      } catch(e) {}
    }

    window.scrollTo({ top: 0, behavior: 'instant' });
  }

  window.closeMobileDetailView = function(isFromPopState = false) {
    if (hasUnsavedChanges) {
      const discard = window.confirm('You have unsaved modifications. Discard and return to menu?');
      if (!discard) return;
      window.discardSettingsChanges();
    }
    const container = document.querySelector('.st-container');
    if (container) {
      container.classList.remove('mobile-detail-open');
    }

    if (!isFromPopState && history.pushState) {
      try {
        const url = new URL(window.location.href);
        url.hash = '';
        url.searchParams.delete('tab');
        url.searchParams.delete('section');
        history.pushState({ mobileDetail: false }, '', url.toString());
      } catch(e) {}
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // 2. Handle Browser / Android System Back Button via popstate
  window.addEventListener('popstate', function(e) {
    if (window.innerWidth <= 768) {
      const isDetailOpen = document.querySelector('.st-container.mobile-detail-open');
      const hash = window.location.hash;
      if (isDetailOpen && (!hash || hash === '#')) {
        window.closeMobileDetailView(true);
      } else if (hash && hash.length > 1) {
        const sec = hash.replace('#', '');
        openMobileDetail(sec, false);
      }
    }
  });

  // 3. Wrap tab switching to manage mobile view state
  const originalSwitch = window.switchSettingsTab;
  if (typeof originalSwitch === 'function') {
    window.switchSettingsTab = function(rawSectionId, updateUrl) {
      const res = originalSwitch(rawSectionId, updateUrl);
      openMobileDetail(rawSectionId, true);
      return res;
    };
  }

  // Hook nav item clicks for mobile view
  document.querySelectorAll('#settingsNav .st-nav-item').forEach(item => {
    item.addEventListener('click', function() {
      const sec = this.dataset.section;
      openMobileDetail(sec, true);
    });
  });

  // If page loads with a specific hash on mobile, drill in
  if (window.location.hash && window.location.hash.length > 1 && window.innerWidth <= 768) {
    const sec = window.location.hash.replace('#', '');
    openMobileDetail(sec, false);
  }

  // 4. Dirty Form Tracking & Sticky Save Bar (Virtual Keyboard Aware)
  const saveBar = document.getElementById('stStickySaveBar');

  function setDirty(isDirty, form) {
    hasUnsavedChanges = isDirty;
    activeFormEl = form || null;
    if (saveBar) {
      saveBar.style.display = isDirty ? 'flex' : 'none';
    }
  }

  document.querySelectorAll('.st-section form').forEach(form => {
    form.addEventListener('input', () => setDirty(true, form));
    form.addEventListener('change', () => setDirty(true, form));
    form.addEventListener('submit', () => setDirty(false, null));
  });

  window.triggerCurrentSectionSave = function() {
    const activeSection = document.querySelector('.st-section.active');
    if (!activeSection) return;
    const form = activeSection.querySelector('form');
    if (form) {
      const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
      if (submitBtn) {
        submitBtn.click();
      } else {
        form.requestSubmit ? form.requestSubmit() : form.submit();
      }
      setDirty(false, null);
    } else {
      if (typeof showStToast === 'function') {
        showStToast('Preferences saved successfully');
      }
      setDirty(false, null);
    }
  };

  window.discardSettingsChanges = function() {
    const activeSection = document.querySelector('.st-section.active');
    if (activeSection) {
      const form = activeSection.querySelector('form');
      if (form) form.reset();
    }
    setDirty(false, null);
    if (typeof showStToast === 'function') {
      showStToast('Modifications discarded');
    }
  };

  // Adjust save bar position above mobile virtual keyboard if open
  if (window.visualViewport && saveBar) {
    const handleViewportChange = () => {
      if (!hasUnsavedChanges || window.innerWidth > 768) return;
      const keyboardHeight = window.innerHeight - window.visualViewport.height;
      if (keyboardHeight > 80) {
        saveBar.style.bottom = `${keyboardHeight + 10}px`;
      } else {
        saveBar.style.bottom = '';
      }
    };
    window.visualViewport.addEventListener('resize', handleViewportChange);
    window.visualViewport.addEventListener('scroll', handleViewportChange);
  }

  window.handleAvatarSelected = function(input) {
    if (!input || !input.files || !input.files[0]) return;
    const file = input.files[0];
    if (!file.type.startsWith('image/')) {
      if (typeof showStToast === 'function') showStToast('Please select a valid image file');
      return;
    }
    const reader = new FileReader();
    reader.onload = function(e) {
      const img = document.getElementById('stAvatarImg');
      const text = document.getElementById('stAvatarText');
      if (img) {
        img.src = e.target.result;
        img.style.display = 'block';
      }
      if (text) text.style.display = 'none';
      setDirty(true, null);
      if (typeof showStToast === 'function') showStToast('Avatar preview updated. Tap Save to apply.');
    };
    reader.readAsDataURL(file);
  };

  window.addEventListener('beforeunload', function(e) {
    if (hasUnsavedChanges) {
      e.preventDefault();
      e.returnValue = 'You have unsaved modifications. Are you sure you want to leave?';
      return e.returnValue;
    }
  });

})();
