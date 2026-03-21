# Security Audit Scope
**WalStream**

This document defines the scope for a third-party security audit prior to mainnet deployment.

---

## Recommended Auditors

Firms with relevant experience in Sui/Move and cryptographic systems:
- **Zellic** — Move smart contract audits, Sui ecosystem
- **OtterSec** — Sui/Move audits, DeFi and NFT protocols
- **Cure53** — Web application and cryptography audits

---

## Audit Scope

### 1. Sui Move Smart Contracts (`smart_contracts/sources/`)

**Priority: Critical**

| Area | File | Concerns |
|---|---|---|
| Access control logic | `access_control.move` | Authorization bypass in `is_authorized`, grant table manipulation, epoch overflow in timed grants |
| Subscription payment | `access_control.move` | Coin splitting correctness, reentrancy via `purchase_access`, revenue address validation |
| Registry integrity | `video_registry.move` | Ownership transfer edge cases, visibility flag manipulation |
| Seal approval gate | `access_control.move` | `seal_approve` abort conditions, identity byte matching correctness |

### 2. Cryptographic Key Management (`utils/`)

**Priority: Critical**

| Area | File | Concerns |
|---|---|---|
| AES-GCM-256 encryption | `utils/crypto.py` | Nonce uniqueness, key derivation, IV reuse risk |
| HMAC-SHA256 signed URLs | `utils/signing.py` | Timing attacks in comparison, secret rotation, expiry enforcement |
| Seal integration | `frontend/src/lib/seal.ts` | Session key TTL, server config authenticity, threshold parameter correctness |
| Encryption key lifecycle | `control_plane/upload.py` | Key generation entropy, server-side key clearance after Seal commit |

### 3. API Security (`control_plane/`, `data_plane/`)

**Priority: High**

| Area | Concerns |
|---|---|
| Authentication & authorisation | API key entropy, timing-safe comparison, rate limit bypass |
| Input validation | Path traversal in HLS file serving, video ID injection, chunk index manipulation |
| File upload handling | MIME type bypass, chunk size limits, session fixation |
| CORS & CSP | Wildcard origin policy appropriateness for production |
| SQL injection | SQLAlchemy text() queries with user input |

### 4. Infrastructure & Deployment

**Priority: Medium**

| Area | Concerns |
|---|---|
| Secret management | `SIGNING_SECRET` rotation, default secret detection |
| Docker configuration | Container privilege escalation, exposed ports, base image vulnerabilities |
| Dependency audit | Python (`requirements.txt`) and npm packages for known CVEs |
| Walrus blob access | Unauthenticated blob retrieval by blob ID, content integrity verification |

---

## Current Security Controls

The following controls are already implemented:

- **HMAC-SHA256** signed playback URLs with expiry enforcement and constant-time comparison (`hmac.compare_digest`)
- **AES-GCM-256** encryption with random 12-byte nonce prepended to ciphertext
- **Path traversal protection** in HLS file serving (`os.path.normpath` + prefix check)
- **Rate limiting** — 300 req/min per API key, 60 req/min per IP (token bucket)
- **Input validation** — Pydantic models on all POST/PATCH endpoints
- **Seal key clearance** — Server deletes plaintext AES key after owner commits Seal blob
- **On-chain access gate** — Every private playback request verified via `devInspectTransactionBlock`

---

## Out of Scope

- Live/RTMP streaming infrastructure (not implemented)
- Frontend XSS/CSRF (mitigated by Next.js defaults; recommend separate frontend audit)
- Walrus protocol-level security (audited by Mysten Labs)
- Sui protocol-level security (audited by Mysten Labs)

---

## Pre-Audit Checklist

Before commissioning the audit:

- [ ] Replace `SIGNING_SECRET` default detection with hard startup failure
- [ ] Restrict CORS `allow_origins` from `["*"]` to explicit production domains
- [ ] Add `Content-Security-Policy` headers to embed player endpoint
- [ ] Pin Docker base image versions
- [ ] Run `pip audit` and `npm audit` and resolve high/critical findings
- [ ] Enable `verifyKeyServers: true` in `frontend/src/lib/seal.ts` for mainnet
