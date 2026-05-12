// p_login.js - Login page specific JavaScript

function showLoading() {
  const loadingPage = document.getElementById('loading-page');
  if (loadingPage) {
    loadingPage.style.display = 'flex';
    loadingPage.setAttribute('aria-label', 'Signing in, please wait');
  }
}

function hideLoading() {
  const loadingPage = document.getElementById('loading-page');
  if (loadingPage) {
    loadingPage.style.display = 'none';
  }
}

// Improved Google login handling
document.addEventListener('DOMContentLoaded', function() {
  const googleBtn = document.getElementById('sign-in-with-google-btn');

  if (googleBtn) {
    googleBtn.addEventListener('click', function() {
      showLoading();

      // Hide loading after a timeout as fallback
      setTimeout(function() {
        const hasError = false; // Replace with actual error checking logic
        if (hasError) {
          hideLoading();
          // Show error message
        } else {
          // Keep loading until actual redirect happens
          // The actual login process will handle hiding the loading
        }
      }, 5000);
    });
  }

  // Hide loading on page show (back button)
  window.addEventListener('pageshow', hideLoading);
});