// File: static/aes_decrypt.js
// AES-CBC decryption using Web Crypto API, key derived from userId + serverSecret (SHA-256)

async function deriveKey(userId, serverSecret) {
    const encoder = new TextEncoder();
    const data = encoder.encode(userId + serverSecret);
    const hash = await crypto.subtle.digest('SHA-256', data);
    return crypto.subtle.importKey(
        'raw',
        hash,
        { name: 'AES-CBC' },
        false,
        ['decrypt']
    );
}

// encryptedData: ArrayBuffer, first 16 bytes are IV, rest is ciphertext
async function decryptAES_CBC(encryptedData, userId, serverSecret) {
    const iv = encryptedData.slice(0, 16);
    const ciphertext = encryptedData.slice(16);
    const key = await deriveKey(userId, serverSecret);
    const decrypted = await crypto.subtle.decrypt(
        { name: 'AES-CBC', iv: new Uint8Array(iv) },
        key,
        ciphertext
    );
    // Remove PKCS7 padding
    const data = new Uint8Array(decrypted);
    const padLen = data[data.length - 1];
    return data.slice(0, data.length - padLen).buffer;
}

// Export for use in other scripts
window.decryptAES_CBC = decryptAES_CBC;
