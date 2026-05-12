/**
 * Client-side File Access History Tracking
 * Call this function whenever a file is viewed/accessed
 */

async function trackFileAccess(fileName, fileType, filePath = '', fileUrl = '') {
    try {
        const response = await fetch('/api/track-file-access', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                file_name: fileName,
                file_type: fileType,
                file_path: filePath,
                file_url: fileUrl
            })
        });

        if (!response.ok) {
            console.warn('Failed to track file access');
        }
    } catch (error) {
        console.error('Error tracking file access:', error);
    }
}

// Export for use in other scripts
if (typeof window !== 'undefined') {
    window.trackFileAccess = trackFileAccess;
}
