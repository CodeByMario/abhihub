/**
 * Client-side File Access History Tracking
 * Call this function whenever a file is viewed/accessed
 */

const fileAccessRequests = new Map();

async function trackFileAccess(fileName, fileType, filePath = '', fileUrl = '') {
    const requestKey = [fileName, fileType, filePath, fileUrl].join('|');
    const existing = fileAccessRequests.get(requestKey);
    if (existing) return existing;

    const requestPromise = (async () => {
    try {
        const startTime = performance.now();
        const response = await fetch('/api/events', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                event_type: 'FILE_ACCESS',
                file_name: fileName,
                file_type: fileType,
                file_path: filePath,
                file_url: fileUrl
            })
        });
        const latency = Math.round(performance.now() - startTime);

        if (!response.ok) {
            console.warn('Failed to track file access');
            if (typeof window.AbhiHubTracking !== 'undefined') {
                window.AbhiHubTracking.trackApiLatency('/api/events', latency, response.status);
            }
        } else {
            // Trigger GA4 event ONLY after backend confirmation (integrity fix)
            if (typeof window.AbhiHubTracking !== 'undefined') {
                // file size and upload date aren't available here, but we pass what we have
                window.AbhiHubTracking.trackFileView(fileName, fileType);
                window.AbhiHubTracking.trackApiLatency('/api/events', latency, response.status);
            }
        }
    } catch (error) {
        console.error('Error tracking file access:', error);
    }
    })();
    fileAccessRequests.set(requestKey, requestPromise);
    requestPromise.finally(() => fileAccessRequests.delete(requestKey));
    return requestPromise;
}

// Export for use in other scripts
if (typeof window !== 'undefined') {
    window.trackFileAccess = trackFileAccess;
}
