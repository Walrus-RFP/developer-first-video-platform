# CDN Integration Guide

This platform is architected to work seamlessly with Content Delivery Networks (CDNs) like Cloudflare, Akamai, or AWS CloudFront to reduce latency and egress costs.

## Architecture

1. **Control Plane**: Handles metadata, API keys, and signing. Should NOT be behind a heavy caching CDN (except for dynamic acceleration).
2. **Data Plane**: Serves HLS assets. Key target for CDN caching.

## Caching Strategy

The Data Plane implements standard `Cache-Control` headers:

- **HLS Segments (`.ts`)**: `public, max-age=31536000, immutable`. 
  - These are immutable blobs on Walrus. Once generated, they never change. 
  - CDNs should cache these indefinitely.
- **HLS Playlists (`.m3u8`)**: `public, max-age=60`.
  - These are small text files. We cache them shortly to allow for updates while still offloading the origin.
- **Thumbnails**: Cached for 24 hours.

## CDN Configuration (Example: Cloudflare)

1. Create a CNAME for your Data Plane (e.g., `cdn.yourplatform.com`).
2. Point it to your origin Data Plane IP/Host.
3. Enable "Proxy status" (Orange Cloud).
4. Create a **Page Rule**:
   - URL: `cdn.yourplatform.com/play/*`
   - Cache Level: "Cache Everything"
   - Edge Cache TTL: Respect Existing Headers

## Signed URLs and CDNs

Since the platform uses query-string based signatures (`?sig=...&exp=...`), you should ensure your CDN is configured to **Include Query String** in the Cache Key. 

If you are using Private/Seal-encrypted videos, the signature ensures only authorized users can fetch the assets from the CDN.

## Security

For production hardening, you should configure your origin Data Plane to ONLY accept traffic from your CDN provider's IP ranges (e.g., [Cloudflare IPs](https://www.cloudflare.com/ips/)).
