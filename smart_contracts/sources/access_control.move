/// access_control.move
///
/// Manages per-video access grants and subscription policies.
/// Works in tandem with video_registry.move — ownership lives there,
/// grants/subscriptions live here.
///
/// Backend usage pattern (devInspectTransactionBlock):
///   Call `is_authorized(registry, store, video_id, user_address)` to gate
///   playback requests without submitting a transaction.
///
/// Access hierarchy (evaluated in order by is_authorized):
///   1. Video owner always has access.
///   2. Video is_public → everyone has access.
///   3. Caller holds a non-expired AccessGrant.
///   4. Otherwise → denied.
module smart_contracts::access_control {
    use sui::table::{Self, Table};
    use sui::coin::{Self, Coin};
    use sui::sui::SUI;
    use sui::event;
    use std::string::String;
    use std::option::{Self, Option};
    use smart_contracts::video_registry::{Registry, borrow_metadata, metadata_owner, metadata_is_public};

    // ── Error codes ──────────────────────────────────────────────────────────
    const ENotOwner:          u64 = 0;
    const EVideoNotFound:     u64 = 1;
    const EGrantAlreadyExists:u64 = 2;
    const EGrantNotFound:     u64 = 3;
    const ENoSubscriptionPolicy:  u64 = 4;
    const EInsufficientPayment:   u64 = 5;

    // ── Core structs ─────────────────────────────────────────────────────────

    /// Shared object — one per deployment.
    public struct AccessStore has key {
        id: UID,
        /// video_id → GrantTable (one GrantTable per video)
        grants: Table<String, GrantTable>,
        /// video_id → SubscriptionPolicy (optional; set by owner)
        policies: Table<String, SubscriptionPolicy>,
    }

    /// Per-video grant map: grantee_address → AccessGrant.
    public struct GrantTable has store {
        entries: Table<address, AccessGrant>,
    }

    /// A single access grant record.
    public struct AccessGrant has store, drop {
        /// None = permanent grant; Some(epoch) = expires at this epoch.
        expires_at: Option<u64>,
        granted_by: address,
        granted_at: u64,
    }

    /// A self-serve subscription policy the owner installs on a video.
    public struct SubscriptionPolicy has store, drop {
        /// Price in MIST (1 SUI = 1_000_000_000 MIST).
        price_mist: u64,
        /// How many epochs the purchased grant lasts.
        duration_epochs: u64,
        /// Where revenue is sent. Typically the video owner's address.
        revenue_address: address,
    }

    // ── Events ───────────────────────────────────────────────────────────────

    public struct AccessGranted has copy, drop {
        video_id: String,
        user: address,
        granted_by: address,
        expires_at: Option<u64>,
        epoch: u64,
    }

    public struct AccessRevoked has copy, drop {
        video_id: String,
        user: address,
        revoked_by: address,
        epoch: u64,
    }

    public struct SubscriptionPolicySet has copy, drop {
        video_id: String,
        owner: address,
        price_mist: u64,
        duration_epochs: u64,
        epoch: u64,
    }

    public struct SubscriptionPurchased has copy, drop {
        video_id: String,
        buyer: address,
        expires_at: u64,
        price_mist: u64,
        epoch: u64,
    }

    // ── Initialiser ──────────────────────────────────────────────────────────

    fun init(ctx: &mut TxContext) {
        transfer::share_object(AccessStore {
            id: object::new(ctx),
            grants: table::new(ctx),
            policies: table::new(ctx),
        });
    }

    // ── Internal helpers ─────────────────────────────────────────────────────

    fun ensure_grant_table(store: &mut AccessStore, video_id: String, ctx: &mut TxContext) {
        if (!table::contains(&store.grants, video_id)) {
            table::add(&mut store.grants, video_id, GrantTable {
                entries: table::new(ctx),
            });
        };
    }

    // ── Entry functions: grants ───────────────────────────────────────────────

    /// Grant permanent access to `user`. Only the video owner may call this.
    public entry fun authorize_user(
        registry: &Registry,
        store: &mut AccessStore,
        video_id: String,
        user: address,
        ctx: &mut TxContext
    ) {
        let meta = borrow_metadata(registry, video_id);
        assert!(metadata_owner(meta) == ctx.sender(), ENotOwner);

        ensure_grant_table(store, video_id, ctx);
        let gt = table::borrow_mut(&mut store.grants, video_id);
        assert!(!table::contains(&gt.entries, user), EGrantAlreadyExists);

        let epoch = ctx.epoch();
        table::add(&mut gt.entries, user, AccessGrant {
            expires_at: option::none(),
            granted_by: ctx.sender(),
            granted_at: epoch,
        });

        event::emit(AccessGranted {
            video_id,
            user,
            granted_by: ctx.sender(),
            expires_at: option::none(),
            epoch,
        });
    }

    /// Grant time-limited access to `user`. Expires at `expire_epoch`.
    /// Only the video owner may call this.
    public entry fun authorize_user_timed(
        registry: &Registry,
        store: &mut AccessStore,
        video_id: String,
        user: address,
        expire_epoch: u64,
        ctx: &mut TxContext
    ) {
        let meta = borrow_metadata(registry, video_id);
        assert!(metadata_owner(meta) == ctx.sender(), ENotOwner);

        ensure_grant_table(store, video_id, ctx);
        let gt = table::borrow_mut(&mut store.grants, video_id);
        assert!(!table::contains(&gt.entries, user), EGrantAlreadyExists);

        let epoch = ctx.epoch();
        let expires = option::some(expire_epoch);

        table::add(&mut gt.entries, user, AccessGrant {
            expires_at: expires,
            granted_by: ctx.sender(),
            granted_at: epoch,
        });

        event::emit(AccessGranted {
            video_id,
            user,
            granted_by: ctx.sender(),
            expires_at: expires,
            epoch,
        });
    }

    /// Revoke a previously granted access. Only the video owner may call this.
    public entry fun revoke_user(
        registry: &Registry,
        store: &mut AccessStore,
        video_id: String,
        user: address,
        ctx: &mut TxContext
    ) {
        let meta = borrow_metadata(registry, video_id);
        assert!(metadata_owner(meta) == ctx.sender(), ENotOwner);
        assert!(table::contains(&store.grants, video_id), EGrantNotFound);

        let gt = table::borrow_mut(&mut store.grants, video_id);
        assert!(table::contains(&gt.entries, user), EGrantNotFound);

        table::remove(&mut gt.entries, user);

        event::emit(AccessRevoked {
            video_id,
            user,
            revoked_by: ctx.sender(),
            epoch: ctx.epoch(),
        });
    }

    // ── Entry functions: subscription policies ────────────────────────────────

    /// Install or replace a subscription policy on a video.
    /// Anyone can then call `purchase_access` to self-serve a timed grant.
    public entry fun set_subscription_policy(
        registry: &Registry,
        store: &mut AccessStore,
        video_id: String,
        price_mist: u64,
        duration_epochs: u64,
        revenue_address: address,
        ctx: &mut TxContext
    ) {
        let meta = borrow_metadata(registry, video_id);
        assert!(metadata_owner(meta) == ctx.sender(), ENotOwner);

        if (table::contains(&store.policies, video_id)) {
            table::remove(&mut store.policies, video_id);
        };

        table::add(&mut store.policies, video_id, SubscriptionPolicy {
            price_mist,
            duration_epochs,
            revenue_address,
        });

        event::emit(SubscriptionPolicySet {
            video_id,
            owner: ctx.sender(),
            price_mist,
            duration_epochs,
            epoch: ctx.epoch(),
        });
    }

    /// Self-serve: pay for access to a private video.
    /// Caller passes a `Coin<SUI>`; the exact `price_mist` is split off and
    /// sent to `revenue_address`; remainder is returned to caller.
    public entry fun purchase_access(
        store: &mut AccessStore,
        video_id: String,
        payment: &mut Coin<SUI>,
        ctx: &mut TxContext
    ) {
        assert!(table::contains(&store.policies, video_id), ENoSubscriptionPolicy);

        let policy = table::borrow(&store.policies, video_id);
        let price = policy.price_mist;
        let duration = policy.duration_epochs;
        let revenue_addr = policy.revenue_address;

        assert!(coin::value(payment) >= price, EInsufficientPayment);

        // Split exact payment and transfer to revenue address.
        let paid = coin::split(payment, price, ctx);
        transfer::public_transfer(paid, revenue_addr);

        let epoch = ctx.epoch();
        let expires_at = epoch + duration;
        let buyer = ctx.sender();

        ensure_grant_table(store, video_id, ctx);
        let gt = table::borrow_mut(&mut store.grants, video_id);

        // Overwrite any existing grant (renew / extend).
        if (table::contains(&gt.entries, buyer)) {
            table::remove(&mut gt.entries, buyer);
        };

        table::add(&mut gt.entries, buyer, AccessGrant {
            expires_at: option::some(expires_at),
            granted_by: buyer,
            granted_at: epoch,
        });

        event::emit(SubscriptionPurchased {
            video_id,
            buyer,
            expires_at,
            price_mist: price,
            epoch,
        });
    }

    // ── Read-only: called via devInspectTransactionBlock ──────────────────────

    /// Primary authorization gate used by the Data Plane backend.
    /// Returns true when the caller is permitted to stream `video_id`.
    ///
    /// Evaluation order:
    ///   1. Owner → always true.
    ///   2. is_public → always true.
    ///   3. Has a non-expired AccessGrant → true.
    ///   4. Otherwise → false.
    public fun is_authorized(
        registry: &Registry,
        store: &AccessStore,
        video_id: String,
        user: address,
        ctx: &TxContext
    ): bool {
        let meta = borrow_metadata(registry, video_id);

        // Rule 1: owner always passes.
        if (metadata_owner(meta) == user) return true;

        // Rule 2: public video — open to all.
        if (metadata_is_public(meta)) return true;

        // Rule 3: check for a valid, non-expired grant.
        if (!table::contains(&store.grants, video_id)) return false;

        let gt = table::borrow(&store.grants, video_id);
        if (!table::contains(&gt.entries, user)) return false;

        let grant = table::borrow(&gt.entries, user);
        if (option::is_none(&grant.expires_at)) {
            true // permanent grant
        } else {
            ctx.epoch() <= *option::borrow(&grant.expires_at) // check expiry
        }
    }

    /// Check whether a subscription policy exists for a video.
    public fun has_subscription_policy(store: &AccessStore, video_id: String): bool {
        table::contains(&store.policies, video_id)
    }

    /// Return subscription price in MIST, or 0 if no policy.
    public fun get_subscription_price(store: &AccessStore, video_id: String): u64 {
        if (!table::contains(&store.policies, video_id)) return 0;
        table::borrow(&store.policies, video_id).price_mist
    }

    /// Called by Mysten Seal key servers (via devInspectTransactionBlock) to
    /// verify a viewer is authorised to receive their share of the decryption key.
    ///
    /// The `id` bytes are the UTF-8 encoding of the video_id string — exactly
    /// the value passed as `id` to SealClient.encrypt() on the client side.
    ///
    /// Seal nodes abort key-share release if this function aborts.
    public fun seal_approve(
        id: vector<u8>,
        registry: &Registry,
        store: &AccessStore,
        ctx: &TxContext,
    ) {
        let video_id = std::string::utf8(id);
        assert!(is_authorized(registry, store, video_id, ctx.sender(), ctx), 0);
    }
}
