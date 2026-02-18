# Architecture
Developer-first Video Infrastructure Platform

This document defines the high-level system architecture.

---

## 1. System Overview

The platform is divided into two main planes:

Control Plane  
Handles metadata, upload sessions, access policies, and developer APIs.

Data Plane  
Handles video chunk storage, aggregation, and delivery.

This separation allows independent scaling and simpler system reasoning.

---

## 2. Core Components

### 2.1 API Gateway

Responsibilities:
- Authenticate requests
- Route requests to services
- Apply rate limiting

Reason:
Provides a single entry point for developers.

---

### 2.2 Control Plane Services

Responsibilities:
- Upload session management
- Video metadata management
- Access policy configuration
- Webhooks and events
- Smart contract integration

Reason:
Separates logic from storage for scalability and clarity.

---

### 2.3 Upload Service

Responsibilities:
- Manage chunked uploads
- Validate chunk order
- Verify checksums
- Generate upload manifest

Reason:
Large video uploads are fragile. Chunking ensures reliability.

---

### 2.4 Walrus Storage

Responsibilities:
- Store video chunks as blobs
- Store manifest metadata
- Support byte-range reads
- Ensure durability

Reason:
Walrus provides durable and portable storage.

---

### 2.5 Processing Service

Responsibilities:
- Validate uploaded video integrity
- Extract metadata like duration and format

Reason:
Minimal processing is needed for project scope.

---

### 2.6 Read Aggregator and Cache

Responsibilities:
- Fetch required chunks
- Reassemble byte ranges
- Serve partial reads efficiently
- Cache frequently accessed data

Reason:
Efficient playback requires fast partial reads.

---

### 2.7 CDN Layer

Responsibilities:
- Cache video segments
- Reduce origin load
- Deliver video globally

Reason:
Compatible with standard delivery patterns.

---

### 2.8 Smart Contract Layer

Responsibilities:
- Store ownership metadata
- Manage access policies
- Enable licensing logic

Reason:
Sui programmable logic required by project.

---

## 3. Upload Flow

1. Developer requests upload session.
2. Client uploads video in chunks.
3. Upload service validates chunks.
4. Chunks stored in Walrus.
5. Manifest created.
6. Metadata registered in control plane.

---

## 4. Playback Flow

1. Viewer requests playback.
2. Access policy verified.
3. Aggregator fetches required byte ranges.
4. CDN caches data.
5. Video streamed to player.

---

## 5. Key Design Decisions

Chunked Uploads  
Reason: Reliable large-file uploads.

Control/Data Plane Separation  
Reason: Independent scaling.

Walrus Storage  
Reason: Durable reusable assets.

Smart Contract Access Control  
Reason: Programmable policies.

Aggregator Layer  
Reason: Efficient playback.

---

## 6. Scalability

- Upload services scale horizontally.
- Walrus storage scales with blobs.
- Aggregator cache scales independently.
- CDN reduces origin load.

---

## 7. Reliability

- Chunk checksums detect corruption.
- Upload retries supported.
- Walrus ensures durability.
- Metrics detect failures early.

---

## 8. Security

- API authentication required.
- Optional encryption.
- Access policies enforced at read time.
- Smart contracts provide auditability.
