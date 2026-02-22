module smart_contracts::video_registry {
    use sui::table::{Self, Table};
    use std::string::String;

    /// Error codes
    const ENotOwner: u64 = 0;
    const EAlreadyRegistered: u64 = 1;

    /// The Registry which tracks all video assets and their authorized users.
    /// This is intended to be a Shared Object.
    public struct Registry has key {
        id: UID,
        assets: Table<String, VideoMetadata>
    }

    /// Metadata for a specific video asset.
    public struct VideoMetadata has store {
        owner: address,
        authorized_users: Table<address, bool>
    }

    /// Capability given to the creator of the module/registry if needed.
    public struct AdminCap has key, store { id: UID }

    fun init(ctx: &mut tx_context::TxContext) {
        let registry = Registry {
            id: object::new(ctx),
            assets: table::new(ctx)
        };
        transfer::share_object(registry);
        
        let admin_cap = AdminCap { id: object::new(ctx) };
        transfer::public_transfer(admin_cap, tx_context::sender(ctx));
    }

    /// Register a new video asset.
    public entry fun register_video(
        registry: &mut Registry,
        video_id: String,
        ctx: &mut tx_context::TxContext
    ) {
        let sender = tx_context::sender(ctx);
        assert!(!table::contains(&registry.assets, video_id), EAlreadyRegistered);

        let metadata = VideoMetadata {
            owner: sender,
            authorized_users: table::new(ctx)
        };
        table::add(&mut registry.assets, video_id, metadata);
    }

    /// Authorize a user to view a video.
    public entry fun authorize_user(
        registry: &mut Registry,
        video_id: String,
        user: address,
        ctx: &mut tx_context::TxContext
    ) {
        let sender = tx_context::sender(ctx);
        let metadata = table::borrow_mut(&mut registry.assets, video_id);
        assert!(metadata.owner == sender, ENotOwner);

        if (!table::contains(&metadata.authorized_users, user)) {
            table::add(&mut metadata.authorized_users, user, true);
        };
    }

    /// De-authorize a user.
    public entry fun revoke_user(
        registry: &mut Registry,
        video_id: String,
        user: address,
        ctx: &mut tx_context::TxContext
    ) {
        let sender = tx_context::sender(ctx);
        let metadata = table::borrow_mut(&mut registry.assets, video_id);
        assert!(metadata.owner == sender, ENotOwner);

        if (table::contains(&metadata.authorized_users, user)) {
            table::remove(&mut metadata.authorized_users, user);
        };
    }

    /// Check if a user is authorized for a video.
    /// This is a read-only check primarily for the backend to query via RPC.
    public fun is_authorized(
        registry: &Registry,
        video_id: String,
        user: address
    ): bool {
        if (!table::contains(&registry.assets, video_id)) return false;
        let metadata = table::borrow(&registry.assets, video_id);
        if (metadata.owner == user) return true;
        table::contains(&metadata.authorized_users, user)
    }
}
