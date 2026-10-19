// Index page initialization
document.addEventListener("DOMContentLoaded", () => {
  // Initialize index-specific components
  if (window.location.hash === '#dashboardSearchSection' || window.location.hash === '#search') {
    setTimeout(() => {
      const sec = document.getElementById('dashboardSearchSection') || document.querySelector('.container_search') || document.querySelector('.ss-search');
      const inp = document.getElementById('searchFileName') || document.getElementById('heroSearchInput');
      if (sec) {
        sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
        if (inp) inp.focus();
      }
    }, 350);
  }
});
