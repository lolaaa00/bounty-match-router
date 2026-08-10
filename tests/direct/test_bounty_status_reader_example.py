"""
Direct-mode tests for the BountyStatusReader worked consumer example.

Scoped deliberately narrowly: every method on this contract makes a
synchronous cross-contract View call via `gl.get_contract_at`-style proxying
against a second, independently-deployed BountyMatchRouter instance, and
gltest-direct 0.29.2 does not support deploying two different `gl.Contract`
subclasses in the same process (confirmed empirically here exactly as noted
in the deliverable-escrow sibling's `test_sequential_grant.py`: it raises
"only one contract is allowed" when a second `gl.Contract` module is loaded
into the same process). Direct-mode tests here therefore only prove the
reader deploys cleanly and stores its configured router address; the actual
cross-contract reads (`describe_bounty`, `is_actionable`, `search_progress`)
are verified against a live router on StudioNet instead - see
tests/integration/test_full_surface.py, which deploys both contracts for
real and exercises the reader against genuine router state. This is the
same honest gap called out in the deliverable-escrow README rather than a
direct-mode test that doesn't really exercise the cross-contract path.
"""

import sys

sys.path.insert(0, "..")
from conftest import as_address  # noqa: E402

READER_CONTRACT = "examples/bounty_status_reader.py"


def test_reader_deploys_and_stores_router_address(direct_deploy, direct_owner):
    reader = direct_deploy(READER_CONTRACT, as_address(direct_owner))
    assert reader is not None


def test_reader_accepts_router_address_as_hex_string(direct_deploy, direct_owner):
    reader = direct_deploy(READER_CONTRACT, as_address(direct_owner).as_hex)
    assert reader is not None
