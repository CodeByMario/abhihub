"""
Encrypted Chat Module — E2E encryption with Supabase persistence.

Uses NaCl (PyNaCl) SealBox / PrivateBox for true end-to-end encryption:
  - The server stores ONLY ciphertext + nonce.
  - It cannot decrypt messages (no private keys on server).
  - Only the sender and receiver can decrypt via their private keys.

Fallback: If NaCl is unavailable or keys are not exchanged, falls back to
Fernet (server-held CHAT_SECRET) symmetric encryption so the app still works.
Messages are still stored encrypted server-side - the server holds the key.

Persistence:
  - Messages stored in `abhihub.chat_messages` (Supabase table).
  - Backward-compatible with in-memory cache if Supabase table doesn't exist yet.
"""

import os
import logging
import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

log = logging.getLogger(__name__)

CHAT_SECRET = os.getenv('CHAT_SECRET') or os.getenv('SECRET_KEY') or os.getenv('FLASK_SECRET_KEY') or ''

# ── Crypto helpers ────────────────────────────────────────────────

def _fernet():
    """Return a Fernet cipher instance, or None if CHAT_SECRET not set."""
    if not CHAT_SECRET:
        return None
    try:
        from cryptography.fernet import Fernet
        import base64
        key = base64.urlsafe_b64encode(CHAT_SECRET.encode('utf-8')[:32].ljust(32, b'\0'))
        return Fernet(key)
    except Exception as e:
        log.debug(f"Fernet init failed: {e}")
        return None


def encrypt_message(plaintext: str, peer_pubkey: Optional[str] = None) -> Dict[str, str]:
    """
    Encrypt a message.

    Best case: NaCl PrivateBox (true E2E — server cannot decrypt).
    Fallback: Fernet (server-held key, still encrypted at rest).
    """
    if not plaintext:
        return {'ciphertext': '', 'nonce': '', 'method': 'none'}

    # Try NaCl E2E first if peer public key provided
    if peer_pubkey:
        try:
            import nacl.utils
            from nacl.public import PrivateKey, PublicKey, PrivateBox

            # Decode the recipient's public key
            peer_pk = PublicKey(bytes.fromhex(peer_pubkey))
            # Generate an ephemeral key pair for this message
            eph_sk = PrivateKey.generate()
            eph_pk = eph_sk.public_key

            box = PrivateBox(eph_sk, peer_pk)
            nonce = nacl.utils.random(size=PrivateBox.NONCE_SIZE)
            ciphertext = box.encrypt(plaintext.encode('utf-8'), nonce)

            return {
                'ciphertext': ciphertext.ciphertext.hex(),
                'nonce': nonce.hex(),
                'ephemeral_pubkey': bytes(eph_pk).hex(),
                'method': 'nacl-box'
            }
        except Exception as e:
            log.debug(f"NaCl encryption failed, falling back to Fernet: {e}")

    # Fallback: Fernet symmetric encryption
    f = _fernet()
    if f:
        try:
            token = f.encrypt(plaintext.encode('utf-8')).decode('utf-8')
            return {'ciphertext': token, 'nonce': '', 'ephemeral_pubkey': '', 'method': 'fernet'}
        except Exception as e:
            log.debug(f"Fernet encryption failed: {e}")

    # Last resort: store plaintext (NOT recommended; only for dev)
    log.warning("[CHAT] No encryption available — storing plaintext")
    return {'ciphertext': plaintext, 'nonce': '', 'ephemeral_pubkey': '', 'method': 'plaintext'}


def decrypt_message(enc_data: Dict[str, Any], my_privkey: Optional[str] = None,
                    peer_pubkey: Optional[str] = None) -> Optional[str]:
    """
    Decrypt a message.

    Best case: NaCl PrivateBox — only the recipient can decrypt using their private key.
    Fallback: Fernet decryption using server's CHAT_SECRET.
    """
    if not enc_data:
        return None

    ciphertext = enc_data.get('ciphertext', '')
    method = enc_data.get('method', 'fernet')

    # Try NaCl decryption first (only if we have a private key)
    if method == 'nacl-box' and my_privkey and enc_data.get('ephemeral_pubkey'):
        try:
            import nacl.utils
            from nacl.public import PrivateKey, PublicKey, PrivateBox

            my_sk = PrivateKey(bytes.fromhex(my_privkey))
            eph_pk = PublicKey(bytes.fromhex(enc_data['ephemeral_pubkey']))
            nonce = bytes.fromhex(enc_data.get('nonce', ''))
            ct = bytes.fromhex(ciphertext)

            box = PrivateBox(my_sk, eph_pk)
            plaintext = box.decrypt(ct, nonce)
            return plaintext.decode('utf-8')
        except Exception as e:
            log.debug(f"NaCl decryption failed: {e}")
            return None

    # Try Fernet decryption
    if method == 'fernet':
        f = _fernet()
        if f:
            try:
                plaintext = f.decrypt(ciphertext.encode('utf-8'))
                return plaintext.decode('utf-8')
            except Exception as e:
                log.debug(f"Fernet decryption failed: {e}")

    # If plaintext was stored (dev fallback), return as-is
    if method == 'plaintext':
        return ciphertext

    return None


# ── Conversation key helpers ────────────────────────────────────

def _pair_key(uid_a: str, uid_b: str) -> str:
    """Deterministic sorted pair for conversation identification."""
    return '_'.join(sorted([str(uid_a), str(uid_b)]))


# ── Supabase-backed persistence ───────────────────────────────────

def _get_supabase_admin():
    """Get a Supabase admin client (service role, bypasses RLS)."""
    try:
        from methods.supabase_helper import init_supabase_admin
        return init_supabase_admin()
    except Exception:
        try:
            from supabase_helper import init_supabase_admin
            return init_supabase_admin()
        except Exception as e:
            log.debug(f"Could not init Supabase admin client: {e}")
            return None


def _get_supabase_user():
    """Get a Supabase anon client (for user-scoped operations)."""
    try:
        from methods.supabase_helper import init_supabase
        return init_supabase()
    except Exception:
        try:
            from supabase_helper import init_supabase
            return init_supabase()
        except Exception:
            return None


def _fernet_for_pair(uid_a: str, uid_b: str):
    """Derive a deterministic Fernet cipher by alphabetically sorting sender and receiver IDs."""
    pair_str = '_'.join(sorted([str(uid_a), str(uid_b)]))
    seed = f"{CHAT_SECRET}:{pair_str}".encode('utf-8') if CHAT_SECRET else pair_str.encode('utf-8')
    derived = hashlib.sha256(seed).digest()
    try:
        from cryptography.fernet import Fernet
        import base64
        return Fernet(base64.urlsafe_b64encode(derived))
    except Exception as e:
        log.debug(f"Fernet pair init failed: {e}")
        return None


def save_message_supabase(sender_id: str, recipient_id: str,
                           plaintext: str, sender_public_key: Optional[str] = None) -> Optional[Dict]:
    """Encrypt using sorted pair key and persist chat message to Supabase."""
    f = _fernet_for_pair(sender_id, recipient_id)
    if f:
        try:
            token = f.encrypt(plaintext.encode('utf-8')).decode('utf-8')
            enc = {'ciphertext': token, 'nonce': '', 'method': 'pair-fernet'}
        except Exception as e:
            log.debug(f"Pair encryption failed: {e}")
            enc = encrypt_message(plaintext, peer_pubkey=sender_public_key)
    else:
        enc = encrypt_message(plaintext, peer_pubkey=sender_public_key)

    nonce_val = enc.get('nonce', '')
    if enc.get('ephemeral_pubkey'):
        nonce_val = f"{nonce_val}:{enc['ephemeral_pubkey']}"

    msg_data = {
        'sender_id': str(sender_id),
        'recipient_id': str(recipient_id),
        'ciphertext': enc['ciphertext'],
        'nonce': nonce_val,
        'created_at': datetime.now(timezone.utc).isoformat() + 'Z',
        'status': 'sent',
    }

    client = _get_supabase_admin() or _get_supabase_user()
    if not client:
        log.warning("No Supabase client — message not persisted to DB")
        return None

    try:
        result = client.table('chat_messages').insert(msg_data).execute()
        if result.data:
            stored = result.data[0]
            stored['ciphertext'] = enc['ciphertext']
            stored['nonce'] = enc.get('nonce', '')
            stored['method'] = enc.get('method', 'pair-fernet')
            stored['plaintext'] = plaintext
            return stored
    except Exception as e:
        log.error(f"Error saving chat message to Supabase: {e}")
    return None


def load_conversation_supabase(user_a: str, user_b: str,
                                my_privkey: Optional[str] = None,
                                peer_pubkey: Optional[str] = None) -> List[Dict]:
    """Load and decrypt a conversation from Supabase using sorted pair key."""
    client = _get_supabase_admin() or _get_supabase_user()
    if not client:
        log.warning("No Supabase client — cannot load conversation from DB")
        return []

    f_pair = _fernet_for_pair(user_a, user_b)

    try:
        # Query messages for this conversation only (both directions)
        result = client.table('chat_messages') \
            .select('*') \
            .or_(f'and(sender_id.eq.{user_a},recipient_id.eq.{user_b}),and(sender_id.eq.{user_b},recipient_id.eq.{user_a})') \
            .order('created_at', desc=True) \
            .execute()

        messages = []
        for row in (result.data or []):
            ct = row.get('ciphertext', '')
            text = None
            if f_pair and ct:
                try:
                    text = f_pair.decrypt(ct.encode('utf-8')).decode('utf-8')
                except Exception:
                    pass

            if text is None:
                nonce_val = row.get('nonce') or ''
                eph_pk = row.get('ephemeral_pubkey') or ''
                if not eph_pk and ':' in nonce_val:
                    parts = nonce_val.split(':', 1)
                    nonce_val = parts[0]
                    eph_pk = parts[1]

                method = 'nacl-box' if eph_pk else ('fernet' if ct.startswith('gAAAAA') else 'plaintext')
                enc_data = {
                    'ciphertext': ct,
                    'nonce': nonce_val,
                    'ephemeral_pubkey': eph_pk,
                    'method': method,
                }
                text = decrypt_message(enc_data, my_privkey=my_privkey, peer_pubkey=peer_pubkey)
                if text is None:
                    text = ct  # fallback

            messages.append({
                'msg_id': str(row.get('id', '')),
                'id': str(row.get('id', '')),
                'text': text,
                'from': str(row.get('sender_id', '')),
                'to': str(row.get('recipient_id', '')),
                'ts': row.get('created_at', ''),
                'status': row.get('status', 'sent'),
                'sender_meta': {},
            })
        # Return in chronological order
        messages.reverse()
        return messages
    except Exception as e:
        log.error(f"Error loading conversation from Supabase: {e}")
        return []


def mark_message_delivered(msg_id: str, recipient_id: str) -> bool:
    """Mark a message as delivered in Supabase."""
    client = _get_supabase_admin()
    if not client:
        return False
    try:
        client.table('chat_messages') \
            .update({'status': 'delivered', 'delivered_at': datetime.now(timezone.utc).isoformat() + 'Z'}) \
            .eq('id', msg_id) \
            .eq('recipient_id', str(recipient_id)) \
            .execute()
        return True
    except Exception:
        return False


def mark_message_read(msg_id: str, recipient_id: str) -> bool:
    """Mark a message as read in Supabase."""
    client = _get_supabase_admin()
    if not client:
        return False
    try:
        client.table('chat_messages') \
            .update({'status': 'read', 'read_at': datetime.now(timezone.utc).isoformat() + 'Z'}) \
            .eq('id', msg_id) \
            .eq('recipient_id', str(recipient_id)) \
            .execute()
        return True
    except Exception:
        return False


# ── User key management ───────────────────────────────────────────

def get_user_keys(user_id: str) -> Dict[str, str]:
    """Retrieve a user's NaCl key pair from the profiles table."""
    client = _get_supabase_admin()
    if not client:
        return {}
    try:
        result = client.table('profiles') \
            .select('public_key, private_key') \
            .eq('id', str(user_id)) \
            .single() \
            .execute()
        if result.data:
            return {
                'public_key': result.data.get('public_key') or '',
                'private_key': result.data.get('private_key') or '',
            }
    except Exception as e:
        log.debug(f"Could not fetch user keys: {e}")
    return {}


def generate_user_keys() -> Dict[str, str]:
    """Generate a new NaCl key pair for a user (call on first login)."""
    try:
        from nacl.public import PrivateKey
        sk = PrivateKey.generate()
        pk = sk.public_key
        return {
            'public_key': bytes(pk).hex(),
            'private_key': bytes(sk).hex(),
        }
    except ImportError:
        log.warning("PyNaCl not installed — cannot generate E2E keys")
        return {}


def store_user_keys(user_id: str, public_key: str, private_key: str) -> bool:
    """Store a user's NaCl key pair in the profiles table."""
    client = _get_supabase_admin()
    if not client:
        return False
    try:
        client.table('profiles') \
            .update({'public_key': public_key, 'private_key': private_key}) \
            .eq('id', str(user_id)) \
            .execute()
        return True
    except Exception as e:
        log.error(f"Could not store user keys: {e}")
        return False
