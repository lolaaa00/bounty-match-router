# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
BountyStatusReader - a worked consumer example for the BountyMatchRouter
primitive. Contains NONE of the router's own machinery: no embeddings, no
cosine similarity, no exec_prompt, no eq_principle call anywhere in this
file - it only calls the router's public View interface.

What it does: a tiny read-only dashboard contract a marketplace frontend
could deploy alongside a router instance. `describe_bounty` calls the
router's `get_bounty` view and reformats the tuple into one human-readable
status line; `is_actionable` tells a caller whether a given address should
currently call `confirm_match` (i.e. whether they are the live proposed
candidate on an open proposal). Neither method holds funds, mutates router
state, or duplicates any of the router's internal ranking/judgement logic -
this is deliberately the thinnest possible integration, proving the
primitive is consumable purely through its public surface.
"""

from genlayer import *


@gl.contract_interface
class IBountyMatchRouter:
    class View:
        def get_bounty(
            self, bounty_id: u256
        ) -> tuple[Address, str, u256, u8, Address, str, str, str, Address, str, str, str]: ...

        def get_tried_count(self, bounty_id: u256) -> u256: ...

    class Write:
        pass


STATUS_LABELS = {
    0: "OPEN",
    1: "PROPOSED",
    2: "MATCHED",
    3: "CANCELLED",
    4: "EXPIRED",
}


class BountyStatusReader(gl.Contract):
    router: Address

    def __init__(self, router: Address):
        router = router if isinstance(router, Address) else Address(router)
        self.router = router

    @gl.public.view
    def describe_bounty(self, bounty_id: u256) -> str:
        proxy = IBountyMatchRouter(self.router)
        (
            poster,
            requirement,
            amount,
            status,
            proposed_candidate,
            proposed_fit,
            _confidence,
            _reason,
            matched_worker,
            _created_at,
            _proposed_at,
            _resolved_at,
        ) = proxy.view().get_bounty(bounty_id)

        label = STATUS_LABELS.get(int(status), "UNKNOWN")
        excerpt = requirement[:80]

        if int(status) == 2:
            return f"#{int(bounty_id)} {label}: matched to {matched_worker.as_hex} for {int(amount)} wei -- \"{excerpt}\""
        if int(status) == 1:
            return (
                f"#{int(bounty_id)} {label}: {proposed_candidate.as_hex} awaiting confirmation "
                f"(fit={proposed_fit}) -- \"{excerpt}\""
            )
        return f"#{int(bounty_id)} {label}: posted by {poster.as_hex} for {int(amount)} wei -- \"{excerpt}\""

    @gl.public.view
    def is_actionable(self, bounty_id: u256, candidate: Address) -> bool:
        """True iff `candidate` is currently the live proposed match on this
        bounty and should call confirm_match on the router directly."""
        candidate = candidate if isinstance(candidate, Address) else Address(candidate)
        proxy = IBountyMatchRouter(self.router)
        (
            _poster,
            _requirement,
            _amount,
            status,
            proposed_candidate,
            _fit,
            _confidence,
            _reason,
            _matched_worker,
            _created_at,
            _proposed_at,
            _resolved_at,
        ) = proxy.view().get_bounty(bounty_id)
        if int(status) != 1:
            return False
        return bytes(proposed_candidate.as_bytes) == bytes(candidate.as_bytes)

    @gl.public.view
    def search_progress(self, bounty_id: u256) -> u256:
        """Convenience passthrough: how many candidates have been tried so
        far on this bounty."""
        proxy = IBountyMatchRouter(self.router)
        return proxy.view().get_tried_count(bounty_id)
