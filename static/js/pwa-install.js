/**
 * PWA Install Handler
 * Manages service worker registration and install prompts
 */

let deferredPrompt;
let isInstalled = false;

// Check if app is already installed
if (window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone) {
    isInstalled = true;
    console.log('[PWA] App is running in standalone mode');
}

// Register service worker
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js')
            .then((registration) => {
                console.log('[PWA] Service Worker registered successfully:', registration.scope);

                // Check for updates periodically
                setInterval(() => {
                    registration.update();
                }, 60000); // Check every minute

                // Listen for updates
                registration.addEventListener('updatefound', () => {
                    const newWorker = registration.installing;
                    console.log('[PWA] New Service Worker found, installing...');

                    newWorker.addEventListener('statechange', () => {
                        if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                            // New service worker available, show update notification
                            showUpdateNotification();
                        }
                    });
                });
            })
            .catch((error) => {
                console.error('[PWA] Service Worker registration failed:', error);
            });
    });
}

// Capture the install prompt event
window.addEventListener('beforeinstallprompt', (e) => {
    console.log('[PWA] Install prompt available');

    // Prevent the default mini-infobar from appearing
    e.preventDefault();

    // Store the event for later use
    deferredPrompt = e;

    // Show custom install button
    showInstallButton();

    // Log install prompt availability
    logInstallPromptEvent('available');
});

// Listen for app installed event
window.addEventListener('appinstalled', (e) => {
    console.log('[PWA] App installed successfully');
    isInstalled = true;

    // Hide install button
    hideInstallButton();

    // Log installation
    logInstallPromptEvent('installed');

    // Clear the deferred prompt
    deferredPrompt = null;

    // Show success message
    showInstallSuccessMessage();
});

// Function to show install button
function showInstallButton() {
    const installButton = document.getElementById('pwa-install-btn');
    const installBanner = document.getElementById('pwa-install-banner');

    if (installButton) {
        installButton.style.display = 'inline-flex';
        installButton.addEventListener('click', handleInstallClick);
    }

    if (installBanner) {
        installBanner.style.display = 'block';
    }
}

// Function to hide install button
function hideInstallButton() {
    const installButton = document.getElementById('pwa-install-btn');
    const installBanner = document.getElementById('pwa-install-banner');

    if (installButton) {
        installButton.style.display = 'none';
    }

    if (installBanner) {
        installBanner.style.display = 'none';
    }
}

// Handle install button click
async function handleInstallClick() {
    if (!deferredPrompt) {
        console.log('[PWA] Install prompt not available');

        // Check if it's iOS
        if (isIOS()) {
            showIOSInstructions();
        }
        return;
    }

    // Show the install prompt
    deferredPrompt.prompt();

    // Wait for the user's response
    const { outcome } = await deferredPrompt.userChoice;
    console.log(`[PWA] User response: ${outcome}`);

    // Log the outcome
    logInstallPromptEvent(outcome);

    if (outcome === 'accepted') {
        console.log('[PWA] User accepted the install prompt');
    } else {
        console.log('[PWA] User dismissed the install prompt');
    }

    // Clear the deferred prompt
    deferredPrompt = null;
}

// Check if device is iOS
function isIOS() {
    return /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
}

// Show iOS install instructions
function showIOSInstructions() {
    const modal = document.getElementById('ios-install-modal');
    if (modal) {
        modal.style.display = 'flex';
    } else {
        // Create modal if it doesn't exist
        createIOSInstructionsModal();
    }
}

// Create iOS instructions modal
function createIOSInstructionsModal() {
    const modal = document.createElement('div');
    modal.id = 'ios-install-modal';
    modal.className = 'pwa-modal';
    modal.innerHTML = `
    <div class="pwa-modal-content">
      <button class="pwa-modal-close" onclick="this.parentElement.parentElement.style.display='none'">&times;</button>
      <h3>Install AbhiHub on iOS</h3>
      <ol class="ios-install-steps">
        <li>Tap the <strong>Share</strong> button <svg width="16" height="16" fill="currentColor"><path d="M8 0l4 4h-3v8H7V4H4l4-4z"/><path d="M0 12h16v4H0z"/></svg> in Safari</li>
        <li>Scroll down and tap <strong>"Add to Home Screen"</strong></li>
        <li>Tap <strong>"Add"</strong> to confirm</li>
      </ol>
    </div>
  `;
    document.body.appendChild(modal);
    modal.style.display = 'flex';
}

// Show update notification
function showUpdateNotification() {
    const notification = document.createElement('div');
    notification.className = 'pwa-update-notification';
    notification.innerHTML = `
    <div class="pwa-update-content">
      <p>A new version of AbhiHub is available!</p>
      <button onclick="window.location.reload()">Update Now</button>
      <button onclick="this.parentElement.parentElement.remove()">Later</button>
    </div>
  `;
    document.body.appendChild(notification);

    // Auto-remove after 10 seconds
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 10000);
}

// Show install success message
function showInstallSuccessMessage() {
    const message = document.createElement('div');
    message.className = 'pwa-success-message';
    message.innerHTML = `
    <div class="pwa-success-content">
      <span class="pwa-success-icon">✓</span>
      <p>AbhiHub installed successfully!</p>
    </div>
  `;
    document.body.appendChild(message);

    // Remove after 3 seconds
    setTimeout(() => {
        message.style.opacity = '0';
        setTimeout(() => message.remove(), 300);
    }, 3000);
}

// Log install prompt events (for analytics)
function logInstallPromptEvent(event) {
    console.log(`[PWA Analytics] Install prompt: ${event}`);

    // Send to analytics if available
    if (typeof gtag !== 'undefined') {
        gtag('event', 'pwa_install', {
            event_category: 'PWA',
            event_label: event
        });
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    // Hide install button if already installed
    if (isInstalled) {
        hideInstallButton();
    }

    // Show iOS instructions button on iOS devices
    if (isIOS() && !isInstalled) {
        const installButton = document.getElementById('pwa-install-btn');
        if (installButton) {
            installButton.textContent = 'Install App';
            installButton.addEventListener('click', showIOSInstructions);
        }
    }
});

console.log('[PWA] Install handler loaded');

// Premium PWA Popup Logic
document.addEventListener('DOMContentLoaded', () => {
    const installAppButton = document.getElementById('installAppButton');
    const pwaPopup = document.getElementById('pwaInstallPopup');
    const pwaPopupClose = document.querySelector('.pwa-popup-close');

    if (installAppButton) {
        // Show button if prompt was captured
        if (deferredPrompt) {
            installAppButton.style.display = 'block';
        }

        installAppButton.addEventListener('click', () => {
            if (deferredPrompt) {
                deferredPrompt.prompt();
                deferredPrompt.userChoice.then((choiceResult) => {
                    if (choiceResult.outcome === 'accepted') {
                        console.log('User accepted the A2HS prompt');
                        localStorage.setItem('appInstalled', 'true');
                        installAppButton.style.display = 'none';
                    } else {
                        console.log('User dismissed the A2HS prompt');
                    }
                    deferredPrompt = null;
                });
            }
        });
    }

    if (pwaPopupClose && pwaPopup) {
        pwaPopupClose.addEventListener('click', () => {
            pwaPopup.style.display = 'none';
        });
    }

    // Also listen for the event again to show the button if it comes later
    window.addEventListener('beforeinstallprompt', () => {
        if (installAppButton) installAppButton.style.display = 'block';
    });

    // Global function for onclick (if still used)
    window.PWAManager = {
        closePWAPopup: () => {
            if (pwaPopup) pwaPopup.style.display = 'none';
        }
    };
});
