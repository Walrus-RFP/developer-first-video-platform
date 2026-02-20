# 2-Week Execution Plan  
Developer-First Video Infrastructure Platform

Team size: 2 people  
Timeline: 14 days  

---

## Team Role Split

| Person | Responsibility |
|--------|----------------|
| Person A | Control Plane (APIs, metadata versioning, smart contracts, access control, SDK, docs) |
| Person B | Data Plane (chunk uploads, manifest, Walrus storage, read aggregator, caching, playback, integrity checks) |

---

# Week 1 — Core Video Pipeline

Goal: Upload → Store → Play video locally with reusable asset support.

---

## Day 1 (16th feb) — Architecture Freeze + Asset Model (DONE)

| Task | Person A | Person B | Output Files | Check |
|------|-----------|-----------|---------------|-------|
| Extract requirements | List API & metadata needs | List storage needs | docs/REQUIREMENTS.md | Scope clear |
| Finalize HLD | Update architecture doc | Validate storage flow | docs/ARCHITECTURE.md | No confusion |
| Define asset model | video_id, owner, version | Review model | docs/ASSET_MODEL.md | Reuse supported |
| Repo setup | Create repo folders | Setup environment | README.md | Repo runs |

---

## Day 2 (17th Feb)— API Spec + Storage Format (DONE)

| Task | Person A | Person B | Output Files | Check |
|------|-----------|-----------|---------------|-------|
| Define APIs | Upload/playback/metadata APIs | Review endpoints | docs/API_SPEC.md | Agreement reached |
| Metadata schema | Versioning + ownership fields | — | docs/METADATA_SCHEMA.md | Asset reusable |
| Chunk format | — | Decide chunk size + naming | docs/STORAGE_FORMAT.md | Fixed format |
| Manifest spec | — | Define manifest structure | docs/MANIFEST.md | Integrity supported |

---

## Day 3 (18th Feb)— Upload Session + Chunk Upload (DONE)

| Task | Person A | Person B | Output Files | Check |
|------|-----------|-----------|---------------|-------|
| Upload session API | POST /upload-session | — | control-plane/upload_api.py | Session works |
| Metadata DB | video_id, owner, version | — | control-plane/db.py | Asset stored |
| Chunk upload handler | — | PUT /upload/{chunk} | data-plane/chunk_handler.py | Chunk saved |
| Checksum validation | — | Validate chunk hash | utils/checksum.py | Corruption detected |

---

## Day 4 (19th Feb)— Resume Upload + Manifest + Versioning (DONE)

| Task | Person A | Person B | Output Files | Check |
|------|-----------|-----------|---------------|-------|
| Resume upload logic | Track uploaded chunks | — | upload_status.py | Resume works |
| Upload complete API | POST /complete | — | upload_complete.py | Upload finalizes |
| Manifest builder | — | Create manifest.json | manifest_builder.py | Manifest correct |
| Version metadata | Store new asset version | — | metadata_version.py | Asset reusable |

---

## Day 5 (20th Feb)— Basic Playback (DONE)

| Task | Person A | Person B | Output Files | Check |
|------|-----------|-----------|---------------|-------|
| Playback URL API | GET /playback-url | — | playback_api.py | URL returned |
| Read service basic | — | Reassemble chunks | read_service.py | Video downloadable |
| Asset reuse test | Use same video twice | — | tests/reuse_test.py | Reuse works |

---

## Day 6 (21st Feb) — Partial Reads + Seek

| Task | Person A | Person B | Output Files | Check |
|------|-----------|-----------|---------------|-------|
| Playback token | Generate secure token | — | auth.py | Token validated |
| Byte-range support | — | Range header support | byte_range.py | Seek works |
| Demo player page | — | HTML player page | demo/player.html | Video plays |

---

## Day 7 (22nd Feb)— Internal Demo + Bug Fix

| Task | Person A | Person B | Output Files | Check |
|------|-----------|-----------|---------------|-------|
| Test reuse cases | Multi-app playback | — | tests/reuse_cases.py | Works |
| Test large uploads | — | Upload big file | tests/upload_test.py | Stable |
| Fix bugs | API fixes | Storage fixes | commits | Pipeline stable |

Week 1 Result: Upload → Store → Play video working.

---

# Week 2 — Walrus + Smart Contracts + Durability

Goal: Production-style demo with durability and access control.

---

## Day 8 (23rd Feb)— Walrus Integration

| Task | Person A | Person B | Output Files | Check |
|------|-----------|-----------|---------------|-------|
| Add Walrus config | Metadata config fields | — | walrus_config.py | Config saved |
| Walrus storage | — | Store chunks as blobs | walrus_upload.py | Stored in Walrus |
| Walrus read | — | Fetch chunk from Walrus | walrus_read.py | Playback works |

---

## Day 9 (24th Feb)— Aggregator + Cache Layer

| Task | Person A | Person B | Output Files | Check |
|------|-----------|-----------|---------------|-------|
| Playback auth check | Validate token | — | playback_auth.py | Secure playback |
| Read aggregator | — | Assemble chunks on demand | aggregator.py | Works |
| Cache layer | — | In-memory cache | cache.py | Faster playback |

---

## Day 10 (25th Feb)— Smart Contracts

| Task | Person A | Person B | Output Files | Check |
|------|-----------|-----------|---------------|-------|
| Write Sui contract | owner + allowed users | — | smart-contracts/video.move | Deploy works |
| Access API | Policy check | — | access_api.py | Private video blocked |
| Playback integration | — | Check access before read | read_auth.py | Unauthorized blocked |

---

## Day 11 (26th Feb)— Durability + Integrity Validation

| Task | Person A | Person B | Output Files | Check |
|------|-----------|-----------|---------------|-------|
| Audit log service | Track uploads & access | — | audit_log.py | Logs stored |
| Integrity job | — | Verify chunk checksums | integrity_check.py | Corruption detected |
| Manifest validation | — | Rebuild video from chunks | manifest_test.py | Validated |

---

## Day 12 (27th Feb)— SDK + Webhooks + Competitive Analysis

| Task | Person A | Person B | Output Files | Check |
|------|-----------|-----------|---------------|-------|
| SDK wrapper | Upload via SDK | — | sdk/python_client.py | SDK works |
| Webhook events | Upload complete event | — | webhook.py | Event works |
| Competitive analysis | Compare with Mux, Cloudflare Stream, AWS Elemental | — | docs/COMPETITIVE.md | Done |

---

## Day 13 (28th Feb)— Observability + GTM + Docs

| Task | Person A | Person B | Output Files | Check |
|------|-----------|-----------|---------------|-------|
| Metrics API | Upload/read stats | — | metrics_api.py | Stats visible |
| Performance tests | — | Stress test uploads | tests/stress.py | Stable |
| GTM strategy | Write GTM doc | — | docs/GTM.md | Done |
| Docs update | Setup guide + README | — | README.md | Complete |

---

## Day 14 (1st Mar)— Final Submission

| Task | Person A | Person B | Output Files | Check |
|------|-----------|-----------|---------------|-------|
| Record demo | Explain architecture | Show upload/playback | demo.mp4 | Clear demo |
| Final review | Fix docs | Fix bugs | repo | Stable |
| Submit project | Upload repo | Upload repo | submission | Done |

---

# Final Outcome

- Chunked resumable upload pipeline
- Walrus-backed durable storage
- Byte-range playback with aggregator + cache
- Smart-contract access control
- Video as reusable asset with versioning
- Developer APIs + SDK
- Observability metrics
- Working demo + documentation
