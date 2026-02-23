# Asset Model
Developer-first Video Infrastructure Platform

This document defines how video assets are represented in the system.

Videos are treated as reusable, durable data assets rather than transient streaming files.

---

## 1. Video Asset Definition

A video asset is defined as:

A collection of video chunks + manifest + metadata + access policies.

Each asset has a unique identifier and may have multiple versions.

---

## 2. Core Fields

Each video asset stores:

video_id  
Unique identifier for the video asset.

owner_id  
User or organization owning the asset.

created_at  
Timestamp when asset created.

updated_at  
Timestamp when asset updated.

status  
Uploading, Processing, Ready, Failed.

manifest_id  
Reference to chunk manifest.

access_policy_id  
Reference to access control policy.

storage_location  
Reference to Walrus storage bucket/blob.

---

## 3. Versioning

Each video asset may have multiple versions.

Example:
- v1 → original upload
- v2 → updated content

Version fields:

version_number  
parent_version  
created_at  

Reason:
Allows updates without losing old content.

---

## 4. Chunk Model

Each video is stored as chunks.

Fields per chunk:

chunk_id  
video_id  
chunk_index  
checksum  
storage_pointer  

Reason:
Supports resumable uploads and partial reads.

---

## 5. Manifest Model

Manifest defines video structure.

Fields:

video_id  
total_chunks  
chunk_order_list  
video_duration  
codec_info  
resolution  

Reason:
Allows reconstruction of video efficiently.

---

## 6. Access Policy Model

Defines who can read video.

Fields:

policy_id  
video_id  
access_type (public/private)  
allowed_users  
contract_reference  

Reason:
Supports private content and smart-contract access control.

---

## 7. Reuse Model

A single video asset can be used by multiple applications.

Example:
Education app + creator platform both use same asset.

Reuse is enabled because storage is separate from application logic.

---

## 8. Integrity Model

Each asset stores:

chunk checksums  
manifest checksum  

Reason:
Detect corruption and ensure long-term reliability.

---

## 9. Why This Model Works

- Supports large uploads
- Supports reuse
- Supports durability
- Supports access control
- Matches project requirements
