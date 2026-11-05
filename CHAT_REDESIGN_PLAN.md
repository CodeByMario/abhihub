# AbhiHub Chat Redesign & Engagement System Plan

This document tracks both the implemented Low-Cost Optimization Plan (Plan 1) and the complete architecture & implementation blueprint for the Scalable Enterprise Protocol (Plan 2).

---

## Plan 1: Low-Cost / High-Speed Client-Driven (Status: COMPLETED ✅)

### Implemented Enhancements:
1. **0ms Optimistic Visual Delivery**:
   - `sendMessage()` appends message bubbles to the DOM instantaneously (`⏱️ pending` state) with zero network wait.
   - Socket ACK and delivery events transition state cleanly: `⏱️` -> `✓ Sent` -> `✓✓ Delivered` -> `✓✓ Read` (colored blue).
2. **Audio-Haptic Gratification Loop**:
   - Native Web Audio API synthesizer (`ChatSound`) generates low-latency, asset-free send chirps (~480Hz-740Hz sine sweep) and gentle 2-tone melodic receive chimes (~660Hz -> 880Hz).
   - Audio chime toggle button (`🔔`/`🔕`) integrated into chat header with persistent preference state.
3. **Variable Anticipation (Typing Indicators)**:
   - Real-time `chat_typing` socket event relay debounced per user keystroke.
   - Smooth 3-dot animated bouncing indicator (`.typing-indicator`) displaying peer's live presence.
4. **Study Streak & Loss Aversion Mechanics**:
   - Computes unique active peer interaction days to award badges (`🔥 X-Day Streak` / `⚡ Study Duo`).
   - Visually displayed in the chat header to incentivize consistent return visits.
5. **Frictionless Academic Icebreakers**:
   - 1-tap quick action chips (`📚 Share PYQ / Notes`, `💡 Quick question`, `⚡ Quick Quiz`) placed directly above the composer to eliminate conversation drop-off.
6. **Integrity & Message Deduplication**:
   - Client-generated collision-resistant `msg_id` (`c_<timestamp>_<nonce>`) passed through SocketIO relay and preserved across reconnects.

---

## Plan 2: Scalable Enterprise Protocol (Status: SPECIFICATION READY FOR VERIFICATION 📋)

### Objective
High-concurrency, end-to-end encrypted peer-to-peer data transport with gamified collaborative study rooms.

### Architecture Overview

```
[Peer A Browser] <====== WebRTC DataChannel (P2P 0ms Direct) ======> [Peer B Browser]
       │                                                                     │
       ├──── Signaling & NAT Traversal (STUN / TURN / WebSocket Relay) ──────┤
       │                                                                     │
       ▼                                                                     ▼
[Local Encrypted IndexedDB]                                        [Local Encrypted IndexedDB]
       │                                                                     │
       └────────────── Encrypted Cold Storage Backup ────────────────────────┘
                                     │
                             [Supabase Database]
```

---

### Implementation Phases for Plan 2

#### Phase 1: WebRTC P2P DataChannel Transport Layer
- **Protocol**: `RTCDataChannel` (Ordered, reliable mode for text/notes; unordered mode for typing & cursor presence).
- **Signaling Flow**:
  1. Peer A sends `chat_rtc_offer` containing SDP offer to Socket.IO signaling server.
  2. Peer B answers with `chat_rtc_answer` containing SDP answer.
  3. ICE candidates exchanged via `chat_rtc_candidate` over existing Socket.IO connection.
  4. Once DataChannel state is `open`, message transfer bypasses server entirely (0 server bandwidth, sub-50ms cross-region latency).
  5. Fallback: Automatic fallback to existing WebSocket relay if symmetric NAT prevents P2P connection.

#### Phase 2: True End-to-End Cryptography (Double Ratchet + X3DH)
- **Key Agreement**: Extended Triple Diffie-Hellman (X3DH) using Curve25519 identity, signed pre-keys, and one-time pre-keys.
- **Message Encryption**: Double Ratchet Algorithm with AES-256-GCM.
  - Every message has a unique ephemeral key derived from the ratchet root chain.
  - Forward secrecy: Even if a session key is compromised, previous messages cannot be decrypted.
  - Break-in recovery: Compromise of an ephemeral key does not compromise future messages.
- **Key Store**: Private keys stored exclusively in browser `crypto.subtle` non-exportable hardware-backed CryptoKey objects.

#### Phase 3: Persistent Encrypted Storage (Client-Side IndexedDB)
- **Engine**: IndexedDB with AES-GCM database-level encryption key derived from user passphrase/device salt.
- **Capabilities**:
  - Full-text client search across past notes and PYQ discussions without exposing plaintext to backend.
  - Zero-storage server liability: Server only stores encrypted ciphertext blobs with 7-day TTL.

#### Phase 4: Psychological Retention & Gamified Academic Features
1. **Synchronized Study Room & Pomodoro**:
   - Shared 25-minute focus session timer synced across peer DataChannels.
   - Real-time "Currently studying: Engineering Physics - Module 2" status banner.
2. **Academic XP & Study Duo Leveling**:
   - Verification points and XP granted when peers share verified PDF notes or PYQ solutions.
   - Level-up unlockable chat themes (Cyberpunk, Academic Parchment, Dark Neon).
3. **Ephemeral Audio & Diagram Snippets**:
   - P2P voice memos (Opus audio) with auto-destruct timers.
   - Synchronized scratchpad/whiteboard for mathematical formulas.
