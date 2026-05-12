import os
import hashlib
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

# Helper to derive a 32-byte AES key from user_id and a server secret
def derive_key(user_id: str, server_secret: str) -> bytes:
    return hashlib.sha256((user_id + server_secret).encode()).digest()

# Encrypt a file with AES (CBC mode)
def encrypt_file(input_path: str, output_path: str, user_id: str, server_secret: str):
    key = derive_key(user_id, server_secret)
    iv = get_random_bytes(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    with open(input_path, 'rb') as f:
        data = f.read()
    # Pad data to 16 bytes
    pad_len = 16 - (len(data) % 16)
    data += bytes([pad_len]) * pad_len
    encrypted = cipher.encrypt(data)
    with open(output_path, 'wb') as f:
        f.write(iv + encrypted)

# Decrypt a file with AES (CBC mode)
def decrypt_file(input_path: str, output_path: str, user_id: str, server_secret: str):
    key = derive_key(user_id, server_secret)
    with open(input_path, 'rb') as f:
        iv = f.read(16)
        encrypted = f.read()
    cipher = AES.new(key, AES.MODE_CBC, iv)
    data = cipher.decrypt(encrypted)
    pad_len = data[-1]
    data = data[:-pad_len]
    with open(output_path, 'wb') as f:
        f.write(data)

# Example usage:
# encrypt_file('example.pdf', 'example_encrypted.bin', 'user123', 'my_server_secret')
# decrypt_file('example_encrypted.bin', 'example_decrypted.pdf', 'user123', 'my_server_secret')
