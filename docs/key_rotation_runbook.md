# BYOK Key Rotation Runbook (MultiFernet)

## Overview
AbhiHub uses cryptography `MultiFernet` to support zero-downtime key rotation for stored student BYOK API keys.

## Rotation Procedure

1. **Generate New Primary Key**:
   Run in Python:
   ```python
   from cryptography.fernet import Fernet
   print(Fernet.generate_key().decode())
   ```

2. **Update Environment Variable (`FERNET_KEYS`)**:
   Set `FERNET_KEYS` in your production environment secret manager with the NEW key first, followed by the OLD key(s) separated by commas:
   ```bash
   FERNET_KEYS="<NEW_KEY>,<OLD_KEY_1>,<OLD_KEY_2>"
   ```

3. **Verify Operation**:
   - New keys saved via `/api/ai/key` are automatically encrypted with `<NEW_KEY>`.
   - Existing keys continue to decrypt seamlessly using `<OLD_KEY_1>`.

4. **Re-encrypt Stored Keys (Optional Migration Script)**:
   ```python
   from methods.ai_provider import rotate_key
   # Read all ciphertexts from ai_profiles where ai_key_enc is not null
   # new_ciphertext = rotate_key(old_ciphertext)
   # update ai_profiles set ai_key_enc = new_ciphertext
   ```

5. **Retire Old Key**:
   Once all ciphertexts are re-encrypted, remove `<OLD_KEY_1>` from `FERNET_KEYS`.
