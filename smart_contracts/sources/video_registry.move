/// video_registry.move
///
/// Tracks video asset ownership on Sui. Each video is identified by its
/// UUID string (matches the `video_id` column in the Control Plane DB).
///
/// Key design decisions:
///   - Registry is a shared object so any transaction can register/update.
///   - VideoMetadata is kept minimal; access grants live in access_control.move.
///   - seal_policy_id links to the Mysten Seal policy for encrypted videos.
///   - version + parent_video_id support the "register new version" workflow.
///   - All state changes emit events so the backend can index them off-chain.
module smart_contracts::video_registry {
    use sui::table::{Self, Table};
    use sui::event;
    use std::string::String;
    use std::option::{Self, Option};

    // ── Error codes ──────────────────────────────────────────────────────────
    const EAlreadyRegistered: u64 = 0;
    const ENotOwner:          u64 = 1;
    const EVideoNotFound:     u64 = 2;

    // ── Core structs ─────────────────────────────────────────────────────────

    /// Shared object — one per deployment. Stores all video metadata.
    public struct Registry has key {
        id: UID,
        assets: Table<String, VideoMetadata>
    }

    /// Per-video metadata stored inside the Registry table.
    public struct VideoMetadata has store {
        owner: address,
        /// true  → anyone can play without an access grant
        /// false → caller must hold a valid AccessGrant (see access_control.move)
        is_public: bool,
        /// Mysten Seal policy object ID. None for unencrypted videos.
        seal_policy_id: Option<ID>,
        /// Sui epoch at time of registration (approximate wall-clock anchor).
        created_epoch: u64,
        /// Incremented on each `register_video_version` call.
        version: u64,
        /// Points to the original video_id when this is a derived version.
        parent_video_id: Option<String>,
        /// SHA-256 hex digest of the original MP4 file. Enables on-chain integrity proofs.
        content_hash: String,
    }

    /// Capability held by the deployer. Not required for normal operations;
    /// reserved for future admin functions (e.g. emergency takedown).
    public struct AdminCap has key, store { id: UID }

    // ── Events ───────────────────────────────────────────────────────────────

    public struct VideoRegistered has copy, drop {
        video_id: String,
        owner: address,
        is_public: bool,
        content_hash: String,
        version: u64,
        epoch: u64,
    }

    public struct VideoVersionRegistered has copy, drop {
        video_id: String,
        parent_video_id: String,
        owner: address,
        version: u64,
        epoch: u64,
    }

    public struct OwnershipTransferred has copy, drop {
        video_id: String,
        old_owner: address,
        new_owner: address,
        epoch: u64,
    }

    public struct VisibilityChanged has copy, drop {
        video_id: String,
        owner: address,
        is_public: bool,
        epoch: u64,
    }

    public struct SealPolicyLinked has copy, drop {
        video_id: String,
        owner: address,
        seal_policy_id: ID,
        epoch: u64,
    }

    // ── Initialiser ──────────────────────────────────────────────────────────

    fun init(ctx: &mut TxContext) {
        transfer::share_object(Registry {
            id: object::new(ctx),
            assets: table::new(ctx),
        });
        transfer::public_transfer(
            AdminCap { id: object::new(ctx) },
            ctx.sender(),
        );
    }

    // ── Entry functions ───────────────────────────────────────────────────────

    /// Register a brand-new video asset.
    /// `is_public`    — set true for open content, false for gated content.
    /// `content_hash` — SHA-256 hex digest of the original MP4 (integrity proof).
    public entry fun register_video(
        registry: &mut Registry,
        video_id: String,
        is_public: bool,
        content_hash: String,
        ctx: &mut TxContext
    ) {
        assert!(!table::contains(&registry.assets, video_id), EAlreadyRegistered);

        let epoch = ctx.epoch();
        let owner = ctx.sender();

        event::emit(VideoRegistered {
            video_id,
            owner,
            is_public,
            content_hash,
            version: 1,
            epoch,
        });

        table::add(&mut registry.assets, video_id, VideoMetadata {
            owner,
            is_public,
            seal_policy_id: option::none(),
            created_epoch: epoch,
            version: 1,
            parent_video_id: option::none(),
            content_hash,
        });
    }

    /// Register a new version of an existing video.
    /// The new `video_id` must be unique; `parent_video_id` must already exist
    /// and be owned by the caller.
    /// `content_hash` — SHA-256 hex digest of this version's MP4.
    public entry fun register_video_version(
        registry: &mut Registry,
        video_id: String,
        parent_video_id: String,
        is_public: bool,
        content_hash: String,
        ctx: &mut TxContext
    ) {
        assert!(!table::contains(&registry.assets, video_id), EAlreadyRegistered);
        assert!(table::contains(&registry.assets, parent_video_id), EVideoNotFound);

        let sender = ctx.sender();
        let parent = table::borrow(&registry.assets, parent_video_id);
        assert!(parent.owner == sender, ENotOwner);

        let new_version = parent.version + 1;
        let epoch = ctx.epoch();

        event::emit(VideoVersionRegistered {
            video_id,
            parent_video_id,
            owner: sender,
            version: new_version,
            epoch,
        });

        table::add(&mut registry.assets, video_id, VideoMetadata {
            owner: sender,
            is_public,
            seal_policy_id: option::none(),
            created_epoch: epoch,
            version: new_version,
            parent_video_id: option::some(parent_video_id),
            content_hash,
        });
    }

    /// Transfer ownership to a new address.
    public entry fun transfer_ownership(
        registry: &mut Registry,
        video_id: String,
        new_owner: address,
        ctx: &mut TxContext
    ) {
        assert!(table::contains(&registry.assets, video_id), EVideoNotFound);
        let metadata = table::borrow_mut(&mut registry.assets, video_id);
        let old_owner = metadata.owner;
        assert!(old_owner == ctx.sender(), ENotOwner);

        metadata.owner = new_owner;
        event::emit(OwnershipTransferred {
            video_id,
            old_owner,
            new_owner,
            epoch: ctx.epoch(),
        });
    }

    /// Toggle the public/private visibility flag.
    public entry fun set_visibility(
        registry: &mut Registry,
        video_id: String,
        is_public: bool,
        ctx: &mut TxContext
    ) {
        assert!(table::contains(&registry.assets, video_id), EVideoNotFound);
        let metadata = table::borrow_mut(&mut registry.assets, video_id);
        assert!(metadata.owner == ctx.sender(), ENotOwner);

        metadata.is_public = is_public;
        event::emit(VisibilityChanged {
            video_id,
            owner: ctx.sender(),
            is_public,
            epoch: ctx.epoch(),
        });
    }

    /// Attach a Mysten Seal policy object ID to an encrypted video.
    /// Call once after deploying the Seal policy for this video.
    public entry fun link_seal_policy(
        registry: &mut Registry,
        video_id: String,
        seal_policy_id: ID,
        ctx: &mut TxContext
    ) {
        assert!(table::contains(&registry.assets, video_id), EVideoNotFound);
        let metadata = table::borrow_mut(&mut registry.assets, video_id);
        assert!(metadata.owner == ctx.sender(), ENotOwner);

        metadata.seal_policy_id = option::some(seal_policy_id);
        event::emit(SealPolicyLinked {
            video_id,
            owner: ctx.sender(),
            seal_policy_id,
            epoch: ctx.epoch(),
        });
    }

    // ── Read-only helpers (called via devInspectTransactionBlock) ─────────────

    public fun get_owner(registry: &Registry, video_id: String): address {
        assert!(table::contains(&registry.assets, video_id), EVideoNotFound);
        table::borrow(&registry.assets, video_id).owner
    }

    public fun is_public_video(registry: &Registry, video_id: String): bool {
        if (!table::contains(&registry.assets, video_id)) return false;
        table::borrow(&registry.assets, video_id).is_public
    }

    public fun video_exists(registry: &Registry, video_id: String): bool {
        table::contains(&registry.assets, video_id)
    }

    public fun get_version(registry: &Registry, video_id: String): u64 {
        assert!(table::contains(&registry.assets, video_id), EVideoNotFound);
        table::borrow(&registry.assets, video_id).version
    }

    public fun get_seal_policy_id(registry: &Registry, video_id: String): Option<ID> {
        assert!(table::contains(&registry.assets, video_id), EVideoNotFound);
        table::borrow(&registry.assets, video_id).seal_policy_id
    }

    /// Package-internal accessor used by access_control.move's is_authorized.
    public(package) fun borrow_metadata(
        registry: &Registry,
        video_id: String
    ): &VideoMetadata {
        assert!(table::contains(&registry.assets, video_id), EVideoNotFound);
        table::borrow(&registry.assets, video_id)
    }

    public fun get_content_hash(registry: &Registry, video_id: String): String {
        assert!(table::contains(&registry.assets, video_id), EVideoNotFound);
        table::borrow(&registry.assets, video_id).content_hash
    }

    public(package) fun metadata_owner(m: &VideoMetadata): address { m.owner }
    public(package) fun metadata_is_public(m: &VideoMetadata): bool  { m.is_public }
}
