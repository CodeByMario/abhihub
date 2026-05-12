// This script integrates encrypted PDF loading with the PDF.js viewer in viewer1.html
// It checks for a locally cached encrypted file, decrypts it, and loads it into PDF.js
// Requires: encryptedFileManager.js, aes_decrypt.js, and PDF.js

// Usage: Place this script after PDF.js and before the PDF.js viewer initialization in viewer1.html

(async function() {
    // Configurable values (replace with actual user/session info)
    const fileId = window.encryptedPdfId || '{{ pdf_name }}'; // Set this from backend or JS context
    const userId = window.currentUserId || 'USER_ID_HERE'; // Set this from backend or JS context
    const serverSecret = window.serverSecret || 'SERVER_SECRET_HERE'; // Never expose real secret in production!

    // Helper to load PDF from decrypted ArrayBuffer
    function loadPdfFromBuffer(buffer) {
        const pdfjsLib = window['pdfjs-dist/build/pdf'];
        pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.9.359/pdf.worker.min.js';
        const loadingTask = pdfjsLib.getDocument({data: buffer});
        loadingTask.promise.then(function(doc) {
            window.pdfDoc = doc;
            window.pageNum = 1;
            window.renderPage(window.pageNum);
        }).catch(function(error) {
            window.showError('Failed to load PDF.');
        });
    }

    // Try to get encrypted file from local storage
    await window.EncryptedFileManager.removeExpiredFiles();
    let fileRecord = await window.EncryptedFileManager.getFile(fileId);
    let encryptedData;
    if (fileRecord) {
        encryptedData = fileRecord.fileData;
    } else {
        // Fetch from server (should return ArrayBuffer)
        const response = await fetch(`/get_encrypted_file?fileId=${fileId}`);
        encryptedData = await response.arrayBuffer();
        await window.EncryptedFileManager.saveFile(fileId, encryptedData, { name: fileId, path: '', type: 'pdf' });
    }

    // Decrypt in browser
    const decryptedBuffer = await window.decryptAES_CBC(encryptedData, userId, serverSecret);
    loadPdfFromBuffer(decryptedBuffer);
})();
