/**
 * WalrusVideo TypeScript/JavaScript SDK
 *
 * Developer-first SDK for the decentralized video platform.
 * Supports Node.js and browser environments.
 *
 * @example
 * ```ts
 * import { WalrusVideo } from '@walrus-video/sdk';
 *
 * const sdk = new WalrusVideo({ apiKey: 'cv_...', apiBase: 'https://api.yourplatform.com' });
 * const videoId = await sdk.uploadVideo('./demo.mp4', { title: 'My First Video' });
 * const url = await sdk.getPlaybackUrl(videoId);
 * ```
 */

export interface WalrusVideoOptions {
  /** API key (cv_...) */
  apiKey: string;
  /** Control Plane base URL. Default: http://localhost:8000 */
  apiBase?: string;
  /** Data Plane base URL. Default: http://localhost:8001 */
  dataPlane?: string;
}

export interface UploadOptions {
  title?: string;
  description?: string;
  tags?: string[];
  isPublic?: boolean;
  /** Chunk size in bytes. Default: 5 MB */
  chunkSize?: number;
  /** Max concurrent chunk uploads. Default: 4 */
  parallel?: number;
  /** Polling timeout in ms. Default: 600_000 (10 min) */
  pollTimeoutMs?: number;
  /** Called with (uploadedChunks, totalChunks) during upload */
  onProgress?: (uploaded: number, total: number) => void;
}

export interface VideoMetadata {
  video_id: string;
  title: string | null;
  description: string | null;
  owner: string | null;
  is_public: boolean;
  status: string;
  file_size: number;
  duration_seconds: number | null;
  content_hash: string | null;
  created_at: string;
}

export interface PlaybackResponse {
  playlist: string;
}

export interface EmbedResponse {
  embed_url: string;
  iframe_html: string;
}

export interface WebhookResponse {
  webhook_id: string;
  url: string;
  events: string[];
  owner: string;
}

export interface ApiKeyResponse {
  api_key: string;
  owner: string;
  name: string;
}

export interface VideoAnalytics {
  video_id: string;
  total_views: number;
  unique_viewers: number;
  egress_bytes: number;
  ingress_bytes: number;
  last_7_days: Array<{ day: string; views: number; bytes: number }>;
}

export interface Metrics {
  metrics: {
    total_videos: number;
    total_storage_bytes: number;
    total_duration_seconds: number;
    webhooks: { total: number; active: number };
    bandwidth: { ingress_total: number; egress_total: number };
    uploads: {
      total: number;
      succeeded: number;
      failed: number;
      in_progress: number;
      success_rate: number;
    };
  };
  owner_distribution: Record<string, number>;
  recent_usage: Array<{ type: string; bytes: number; timestamp: string }>;
}

export interface VersionResponse {
  video_id: string;
  parent_video_id: string;
  sui_package_id: string | null;
  sui_registry_id: string | null;
}

export interface SubscriptionPolicy {
  has_policy: boolean;
  price_mist?: number;
}

export interface SubscriptionPolicyCreate {
  price_mist: number;
  duration_epochs: number;
  revenue_address: string;
}

export interface SealPolicyResponse {
  linked: boolean;
  seal_policy_id: string | null;
}

// ── Fetch helper ──────────────────────────────────────────────────────────────

async function apiFetch<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  const resp = await fetch(url, options);
  if (!resp.ok) {
    const body = await resp.text().catch(() => "");
    throw new Error(`HTTP ${resp.status}: ${body}`);
  }
  return resp.json() as Promise<T>;
}

// ── SDK class ─────────────────────────────────────────────────────────────────

export class WalrusVideo {
  private readonly apiKey: string;
  private readonly apiBase: string;
  private readonly dataPlane: string;

  constructor(options: WalrusVideoOptions) {
    this.apiKey = options.apiKey;
    this.apiBase = (options.apiBase ?? "http://localhost:8000").replace(/\/$/, "");
    this.dataPlane = (options.dataPlane ?? "http://localhost:8001").replace(/\/$/, "");
  }

  private get authHeaders(): Record<string, string> {
    return { "X-API-Key": this.apiKey };
  }

  // ── Upload ──────────────────────────────────────────────────────────────────

  /**
   * Upload a video file and return the video_id.
   * Supports resumable uploads: chunks already on the server are skipped.
   *
   * Works in both Node.js (pass a file path string) and browser (pass a File/Blob).
   */
  async uploadVideo(
    source: string | File | Blob,
    options: UploadOptions = {}
  ): Promise<string> {
    const {
      title,
      description,
      tags,
      isPublic = true,
      chunkSize = 5 * 1024 * 1024,
      parallel = 4,
      pollTimeoutMs = 600_000,
      onProgress,
    } = options;

    // Resolve blob
    let blob: Blob;
    if (typeof source === "string") {
      // Node.js: read file from path using fs
      const fs = await import("fs").catch(() => null);
      if (!fs) throw new Error("File path strings only supported in Node.js");
      const data = fs.readFileSync(source);
      blob = new Blob([data]);
    } else {
      blob = source;
    }

    const fileSize = blob.size;
    const totalChunks = Math.ceil(fileSize / chunkSize);

    // 1. Create upload session
    const sessData = await apiFetch<{ upload_session_id: string }>(
      `${this.apiBase}/v1/upload-session`,
      { method: "POST", headers: this.authHeaders }
    );
    const sessionId = sessData.upload_session_id;

    // 2. Check already-uploaded chunks (resume support)
    let uploaded = new Set<number>();
    try {
      const sessionStatus = await fetch(
        `${this.dataPlane}/v1/upload-session/${sessionId}`
      );
      if (sessionStatus.ok) {
        const d = await sessionStatus.json();
        uploaded = new Set<number>(d.uploaded_chunks ?? []);
      }
    } catch {
      // ignore — start fresh
    }

    // 3. Upload missing chunks in parallel batches
    const pending = Array.from({ length: totalChunks }, (_, i) => i).filter(
      (i) => !uploaded.has(i)
    );
    let completed = totalChunks - pending.length;
    onProgress?.(completed, totalChunks);

    const uploadChunk = async (idx: number): Promise<void> => {
      const start = idx * chunkSize;
      const end = Math.min(fileSize, start + chunkSize);
      const chunk = blob.slice(start, end);
      const formData = new FormData();
      formData.append("file", chunk, `chunk_${idx}`);

      for (let attempt = 1; attempt <= 3; attempt++) {
        const resp = await fetch(
          `${this.dataPlane}/v1/upload-chunk/${sessionId}/chunk_${idx}/${idx}`,
          { method: "POST", body: formData }
        );
        if (resp.ok) return;
        const err = await resp.text().catch(() => "unknown");
        if (attempt === 3)
          throw new Error(`Chunk ${idx} failed after 3 attempts: ${err}`);
        await new Promise((r) => setTimeout(r, 500 * attempt));
      }
    };

    for (let i = 0; i < pending.length; i += parallel) {
      const batch = pending.slice(i, i + parallel);
      await Promise.all(batch.map((idx) => uploadChunk(idx)));
      completed += batch.length;
      onProgress?.(completed, totalChunks);
    }

    // 4. Kick off async completion
    const params = new URLSearchParams();
    params.set("is_public", String(isPublic));
    if (title) params.set("title", title);
    if (description) params.set("description", description);
    if (tags?.length) params.set("tags", tags.join(","));

    await apiFetch(
      `${this.apiBase}/v1/complete-upload/${sessionId}?${params}`,
      { method: "POST", headers: this.authHeaders }
    );

    // 5. Poll for completion
    const deadline = Date.now() + pollTimeoutMs;
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 3000));
      const statusData = await apiFetch<{
        status: string;
        video_id?: string;
        error?: string;
      }>(`${this.apiBase}/v1/upload-status/${sessionId}`);

      if (statusData.status === "upload completed") {
        return statusData.video_id!;
      }
      if (statusData.status === "failed") {
        throw new Error(`Video processing failed: ${statusData.error}`);
      }
    }

    throw new Error(
      `Video processing did not complete within ${pollTimeoutMs / 1000}s`
    );
  }

  // ── Playback ────────────────────────────────────────────────────────────────

  /** Get a signed HLS playlist URL, optionally gated by Sui on-chain permission. */
  async getPlaybackUrl(videoId: string, userAddress?: string): Promise<string> {
    const params = userAddress
      ? `?user_address=${encodeURIComponent(userAddress)}`
      : "";
    const data = await apiFetch<PlaybackResponse>(
      `${this.apiBase}/v1/playback-url/${videoId}${params}`
    );
    return data.playlist;
  }

  /** Get embed URL and iframe HTML for cross-application video reuse. */
  async getEmbed(videoId: string, userAddress?: string): Promise<EmbedResponse> {
    const params = userAddress
      ? `?user_address=${encodeURIComponent(userAddress)}`
      : "";
    return apiFetch<EmbedResponse>(
      `${this.apiBase}/v1/videos/${videoId}/embed${params}`
    );
  }

  // ── Video Metadata ──────────────────────────────────────────────────────────

  async getVideo(videoId: string): Promise<VideoMetadata> {
    return apiFetch<VideoMetadata>(`${this.apiBase}/v1/videos/${videoId}`);
  }

  async listVideos(owner?: string): Promise<VideoMetadata[]> {
    const params = owner ? `?owner=${encodeURIComponent(owner)}` : "";
    const data = await apiFetch<{ videos: VideoMetadata[] }>(
      `${this.apiBase}/v1/videos${params}`
    );
    return data.videos;
  }

  async updateVideo(
    videoId: string,
    updates: { title?: string; description?: string; isPublic?: boolean }
  ): Promise<VideoMetadata> {
    const payload: Record<string, unknown> = {};
    if (updates.title !== undefined) payload.title = updates.title;
    if (updates.description !== undefined) payload.description = updates.description;
    if (updates.isPublic !== undefined) payload.is_public = updates.isPublic;
    return apiFetch<VideoMetadata>(`${this.apiBase}/v1/videos/${videoId}`, {
      method: "PATCH",
      headers: { ...this.authHeaders, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  async deleteVideo(videoId: string): Promise<boolean> {
    const resp = await fetch(`${this.apiBase}/v1/videos/${videoId}`, {
      method: "DELETE",
      headers: this.authHeaders,
    });
    return resp.status === 200;
  }

  // ── Webhooks ────────────────────────────────────────────────────────────────

  /** Register a webhook to receive platform events. */
  async registerWebhook(
    url: string,
    events: string[] = ["*"]
  ): Promise<WebhookResponse> {
    return apiFetch<WebhookResponse>(`${this.apiBase}/v1/webhooks`, {
      method: "POST",
      headers: { ...this.authHeaders, "Content-Type": "application/json" },
      body: JSON.stringify({ url, events }),
    });
  }

  async listWebhooks(): Promise<WebhookResponse[]> {
    const data = await apiFetch<{ webhooks: WebhookResponse[] }>(
      `${this.apiBase}/v1/webhooks`,
      { headers: this.authHeaders }
    );
    return data.webhooks;
  }

  async deleteWebhook(webhookId: string): Promise<boolean> {
    const resp = await fetch(`${this.apiBase}/v1/webhooks/${webhookId}`, {
      method: "DELETE",
      headers: this.authHeaders,
    });
    return resp.status === 200;
  }

  /**
   * Verify an incoming webhook signature.
   * Use in your webhook receiver endpoint.
   *
   * @example
   * ```ts
   * const isValid = await WalrusVideo.verifyWebhookSignature(rawBody, sigHeader, secret);
   * if (!isValid) return res.status(401).send('Unauthorized');
   * ```
   */
  static async verifyWebhookSignature(
    payload: Uint8Array | string,
    signatureHeader: string,
    secret: string
  ): Promise<boolean> {
    const enc = new TextEncoder();
    const keyData = typeof secret === "string" ? enc.encode(secret) : secret;
    const msgData =
      typeof payload === "string" ? enc.encode(payload) : payload;

    const key = await crypto.subtle.importKey(
      "raw",
      keyData,
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"]
    );
    const sig = await crypto.subtle.sign("HMAC", key, msgData);
    const hex = Array.from(new Uint8Array(sig))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
    const expected = `sha256=${hex}`;

    // Constant-time comparison
    if (expected.length !== signatureHeader.length) return false;
    let diff = 0;
    for (let i = 0; i < expected.length; i++) {
      diff |= expected.charCodeAt(i) ^ signatureHeader.charCodeAt(i);
    }
    return diff === 0;
  }

  // ── API Keys ────────────────────────────────────────────────────────────────

  async generateApiKey(name: string, owner: string): Promise<ApiKeyResponse> {
    return apiFetch<ApiKeyResponse>(`${this.apiBase}/v1/api-keys`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ owner, name }),
    });
  }

  async listApiKeys(owner: string): Promise<ApiKeyResponse[]> {
    const data = await apiFetch<{ api_keys: ApiKeyResponse[] }>(
      `${this.apiBase}/v1/api-keys/${encodeURIComponent(owner)}`
    );
    return data.api_keys;
  }

  // ── Analytics ───────────────────────────────────────────────────────────────

  /** Per-video analytics: views, bandwidth, daily breakdown. */
  async getVideoAnalytics(videoId: string): Promise<VideoAnalytics> {
    return apiFetch<VideoAnalytics>(
      `${this.apiBase}/v1/videos/${videoId}/analytics`,
      { headers: this.authHeaders }
    );
  }

  /** Platform-wide metrics: total videos, storage, bandwidth, upload success rate. */
  async getMetrics(): Promise<Metrics> {
    return apiFetch<Metrics>(`${this.apiBase}/v1/metrics`);
  }

  // ── Video Versioning ─────────────────────────────────────────────────────────

  /**
   * Register a new version of a video.
   * Returns Sui transaction parameters for the caller to sign.
   */
  async createVideoVersion(
    newVideoId: string,
    parentVideoId: string,
    options: { title?: string; description?: string; isPublic?: boolean } = {}
  ): Promise<VersionResponse> {
    const payload: Record<string, unknown> = {
      parent_video_id: parentVideoId,
      is_public: options.isPublic ?? true,
    };
    if (options.title !== undefined) payload.title = options.title;
    if (options.description !== undefined) payload.description = options.description;
    return apiFetch<VersionResponse>(
      `${this.apiBase}/v1/videos/${newVideoId}/version`,
      {
        method: "POST",
        headers: { ...this.authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );
  }

  // ── Subscription Policies ────────────────────────────────────────────────────

  /** Get the on-chain subscription policy for a video. */
  async getSubscriptionPolicy(videoId: string): Promise<SubscriptionPolicy> {
    return apiFetch<SubscriptionPolicy>(
      `${this.apiBase}/v1/subscription/${videoId}`
    );
  }

  /**
   * Returns Sui transaction parameters for the caller to sign.
   * The wallet executes access_control::set_subscription_policy on-chain.
   */
  async createSubscriptionPolicy(
    videoId: string,
    policy: SubscriptionPolicyCreate
  ): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>(
      `${this.apiBase}/v1/subscription/${videoId}`,
      {
        method: "POST",
        headers: { ...this.authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify(policy),
      }
    );
  }

  // ── Seal Key Management ──────────────────────────────────────────────────────

  /**
   * One-time retrieval of the plaintext AES key for a private video.
   * Call immediately after upload, before Seal setup.
   * Returns base64-encoded AES-GCM-256 key.
   * Throws 404 if the key has already been cleared (Seal setup complete).
   */
  async getEncryptionKey(videoId: string): Promise<string> {
    const data = await apiFetch<{ encryption_key_b64: string }>(
      `${this.apiBase}/v1/videos/${videoId}/encryption-key`,
      { headers: this.authHeaders }
    );
    return data.encryption_key_b64;
  }

  /**
   * Commit the Walrus blob ID of the Seal-encrypted AES key.
   * Clears the plaintext key from the server permanently.
   * After this call, only the Seal SDK can distribute the key to authorised viewers.
   */
  async commitSealKey(videoId: string, sealKeyBlobId: string): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>(
      `${this.apiBase}/v1/videos/${videoId}/seal-key`,
      {
        method: "POST",
        headers: { ...this.authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify({ seal_key_blob_id: sealKeyBlobId }),
      }
    );
  }

  /**
   * Upload a Seal-encrypted key blob to Walrus via the data plane.
   * Returns the blob_id to pass to commitSealKey().
   */
  async uploadSealBlob(encryptedKeyBytes: Uint8Array): Promise<string> {
    const data = await apiFetch<{ blob_id: string }>(
      `${this.dataPlane}/v1/seal-blob`,
      {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: encryptedKeyBytes,
      }
    );
    return data.blob_id;
  }

  /** Download a Seal-encrypted key blob from Walrus via the data plane. */
  async downloadSealBlob(blobId: string): Promise<Uint8Array> {
    const resp = await fetch(`${this.dataPlane}/v1/seal-blob/${blobId}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: failed to fetch seal blob`);
    return new Uint8Array(await resp.arrayBuffer());
  }

  // ── Seal Policy ──────────────────────────────────────────────────────────────

  /** Get the Mysten Seal policy linked to a video, if any. */
  async getSealPolicy(videoId: string): Promise<SealPolicyResponse> {
    return apiFetch<SealPolicyResponse>(
      `${this.apiBase}/v1/videos/${videoId}/seal-policy`
    );
  }

  /**
   * Returns Sui transaction parameters to link a Mysten Seal policy to a video.
   * The caller must sign and execute the returned transaction.
   */
  async linkSealPolicy(
    videoId: string,
    sealPolicyId: string
  ): Promise<Record<string, unknown>> {
    return apiFetch<Record<string, unknown>>(
      `${this.apiBase}/v1/videos/${videoId}/seal-policy`,
      {
        method: "POST",
        headers: { ...this.authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify({ seal_policy_id: sealPolicyId }),
      }
    );
  }
}

export default WalrusVideo;
