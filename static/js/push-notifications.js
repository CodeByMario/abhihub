/**
 * AbhiHub Push Notification Client
 * Handles push notification subscription and permission management
 */

const PushNotifications = {
    VAPID_KEY_URL: '/api/push/vapid-public-key',
    SUBSCRIBE_URL: '/api/push/subscribe',
    UNSUBSCRIBE_URL: '/api/push/unsubscribe',
    STATUS_URL: '/api/push/status',

    /**
     * Check if push notifications are supported
     */
    isSupported() {
        return 'Notification' in window &&
            'serviceWorker' in navigator &&
            'PushManager' in window;
    },

    /**
     * Request notification permission
     */
    async requestPermission() {
        if (!this.isSupported()) {
            console.log('[Push] Not supported');
            return false;
        }

        const permission = await Notification.requestPermission();
        return permission === 'granted';
    },

    /**
     * Get current subscription status
     */
    async getSubscription() {
        if (!this.isSupported()) return null;

        const registration = await navigator.serviceWorker.ready;
        return await registration.pushManager.getSubscription();
    },

    /**
     * Subscribe to push notifications
     */
    async subscribe() {
        try {
            const permission = await this.requestPermission();
            if (!permission) {
                console.log('[Push] Permission denied');
                return { success: false, error: 'Permission denied' };
            }

            // Get VAPID public key from server
            const keyResponse = await fetch(this.VAPID_KEY_URL);
            if (!keyResponse.ok) {
                return { success: false, error: 'Push not configured on server' };
            }
            const { publicKey } = await keyResponse.json();

            // Get service worker registration
            const registration = await navigator.serviceWorker.ready;

            // Subscribe to push
            const subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: this.urlBase64ToUint8Array(publicKey)
            });

            // Send subscription to backend
            const response = await fetch(this.SUBSCRIBE_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ subscription: subscription.toJSON() })
            });

            if (response.ok) {
                console.log('[Push] Subscription successful');
                return { success: true };
            } else {
                const data = await response.json();
                return { success: false, error: data.error || 'Subscription failed' };
            }
        } catch (error) {
            console.error('[Push] Subscription error:', error);
            return { success: false, error: error.message };
        }
    },

    /**
     * Unsubscribe from push notifications
     */
    async unsubscribe() {
        try {
            const registration = await navigator.serviceWorker.ready;
            const subscription = await registration.pushManager.getSubscription();

            if (subscription) {
                await subscription.unsubscribe();
                await fetch(this.UNSUBSCRIBE_URL, { method: 'DELETE' });
                console.log('[Push] Unsubscribed');
                return { success: true };
            }
            return { success: false, error: 'No subscription found' };
        } catch (error) {
            console.error('[Push] Unsubscribe error:', error);
            return { success: false, error: error.message };
        }
    },

    /**
     * Toggle subscription status
     */
    async toggle() {
        const subscription = await this.getSubscription();
        if (subscription) {
            return await this.unsubscribe();
        } else {
            return await this.subscribe();
        }
    },

    /**
     * Convert VAPID key from base64 to Uint8Array
     */
    urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding)
            .replace(/-/g, '+')
            .replace(/_/g, '/');
        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    },

    /**
     * Initialize and return current status
     */
    async init() {
        if (!this.isSupported()) {
            return { supported: false, subscribed: false };
        }

        const subscription = await this.getSubscription();
        return {
            supported: true,
            subscribed: !!subscription,
            permission: Notification.permission
        };
    }
};

// Auto-init on load and expose globally
if (typeof window !== 'undefined') {
    window.PushNotifications = PushNotifications;

    // Optional: Add to install popup features if it exists
    document.addEventListener('DOMContentLoaded', async () => {
        const status = await PushNotifications.init();
        console.log('[Push] Status:', status);
    });
}
