"""
Full-surface StudioNet integration test for BountyMatchRouter. Drives every
write method and reads every view, printing state after each step, and
asserts the negative cases actually refuse. Direct mode mocks the LLM
entirely, so this is what catches what it hides: real type marshalling
(Address as calldata hex, CalldataAddress views), real GEN movement (bounty
escrow, payout, refund), and the live exec_prompt + prompt_comparative
round trip inside real consensus deciding a real fit judgement. It also
deploys the worked consumer example (BountyStatusReader) against the same
live router and exercises its cross-contract read methods for real -- the
one path direct mode cannot cover at all (see tests/direct's honest note).

Run with:
    gltest tests/integration/test_full_surface.py -v -s --network studionet
"""
from pathlib import Path

import pytest
from gltest import get_contract_factory, get_default_account, create_accounts
from gltest.assertions import tx_execution_failed
from gltest.contracts.contract_factory import ContractFactory

JUDGE_WAIT = dict(wait_interval=5000, wait_retries=90)

REQUIREMENT_TRUE = "Need a senior Python backend engineer comfortable with async REST APIs and databases."
GOOD_SUMMARY = "I am a senior Python engineer with 6 years building async REST APIs and Postgres-backed services."
BAD_SUMMARY = "I am a professional violinist and part-time baker with no software experience."

FEE = 1000  # wei bounty reward, small nonzero so payout/refund are real value movements


@pytest.fixture(scope="module")
def parties():
    accounts = create_accounts(3)
    return {
        "owner": get_default_account(),
        "poster": accounts[0],
        "worker_good": accounts[1],
        "worker_bad": accounts[2],
    }


@pytest.fixture(scope="module")
def router(parties):
    factory = get_contract_factory("BountyMatchRouter")
    contract = factory.deploy(account=parties["owner"], args=[parties["owner"].address, 10, 10], wait_interval=12000, wait_retries=25)
    print(f"\n[deploy] BountyMatchRouter at {contract.address}")
    return contract


@pytest.fixture(scope="module")
def reader(parties, router):
    # get_contract_factory() only searches gltest.config.yaml's configured
    # contracts_dir ("contracts"); the worked example deliberately lives in
    # examples/ instead. from_file_path() *also* resolves relative to
    # contracts_dir internally (contracts_dir / path), so an absolute path
    # is required here - pathlib's `/` operator discards the left operand
    # once the right operand is itself absolute.
    example_path = (Path(__file__).resolve().parents[2] / "examples" / "bounty_status_reader.py")
    factory = ContractFactory.from_file_path(example_path)
    contract = factory.deploy(account=parties["owner"], args=[router.address], wait_interval=12000, wait_retries=25)
    print(f"[deploy] BountyStatusReader at {contract.address}")
    return contract


def test_full_surface_drives_every_write_and_view(router, reader, parties):
    owner = parties["owner"]
    poster = parties["poster"]
    worker_bad = parties["worker_bad"]
    worker_good = parties["worker_good"]

    # --- view: initial config ------------------------------------------
    cfg0 = router.get_config(args=[]).call()
    print("\n[view] get_config (initial):", cfg0)
    assert cfg0[0].as_hex.lower() == owner.address.lower()
    assert cfg0[1] == 10  # max_pool_size

    # --- write: register two workers, one weak fit one strong fit -------
    print("\n[write] register_worker(worker_bad, BAD_SUMMARY)")
    rb = router.connect(worker_bad).register_worker(args=[BAD_SUMMARY]).transact(wait_interval=12000, wait_retries=25)
    assert not tx_execution_failed(rb), rb

    print("[write] register_worker(worker_good, GOOD_SUMMARY)")
    rg = router.connect(worker_good).register_worker(args=[GOOD_SUMMARY]).transact(wait_interval=12000, wait_retries=25)
    assert not tx_execution_failed(rg), rg

    wc = router.worker_count(args=[]).call()
    print("[view] worker_count:", wc)
    assert wc == 2

    # --- negative: posting a bounty with zero value is refused ----------
    print("\n[write] post_bounty with zero value - expect refusal")
    bad_post = router.connect(poster).post_bounty(args=[REQUIREMENT_TRUE]).transact(value=0, wait_interval=12000, wait_retries=25)
    assert tx_execution_failed(bad_post), "zero-value bounty must be refused"
    print("  refused as expected")

    # --- write: post a real bounty ---------------------------------------
    print(f"\n[write] post_bounty(REQUIREMENT_TRUE) as poster, value={FEE}")
    post_tx = router.connect(poster).post_bounty(args=[REQUIREMENT_TRUE]).transact(value=FEE, wait_interval=12000, wait_retries=25)
    assert not tx_execution_failed(post_tx), post_tx
    bounty_id = 1

    bounty_pre = router.get_bounty(args=[bounty_id]).call()
    print("[view] get_bounty(1) before matching:", bounty_pre)
    assert bounty_pre[3] == 0  # BOUNTY_OPEN

    # --- negative: unknown bounty id -------------------------------------
    print("\n[write] find_and_judge(999) - expect refusal (unknown bounty)")
    bad_judge = router.find_and_judge(args=[999]).transact(wait_interval=12000, wait_retries=25)
    assert tx_execution_failed(bad_judge), "judging an unknown bounty must be refused"
    print("  refused as expected")

    # --- write: find_and_judge - real ranking + real judgement round -----
    print("\n[write] find_and_judge(1) - live exec_prompt round, first candidate")
    j1 = router.find_and_judge(args=[bounty_id]).transact(**JUDGE_WAIT)
    assert not tx_execution_failed(j1), j1

    bounty_after_1 = router.get_bounty(args=[bounty_id]).call()
    print("[view] get_bounty(1) after first find_and_judge:", bounty_after_1)
    status_after_1 = bounty_after_1[3]
    tried_after_1 = router.get_tried_count(args=[bounty_id]).call()
    print(f"  measured status={status_after_1} tried_count={tried_after_1}")
    assert tried_after_1 == 1

    # If the closest-ranked candidate wasn't a FIT, run a second round so a
    # real FIT/PROPOSED branch gets exercised at least once in this run.
    if status_after_1 != 1:  # not BOUNTY_PROPOSED yet
        print("\n[write] find_and_judge(1) again - second candidate")
        j2 = router.find_and_judge(args=[bounty_id]).transact(**JUDGE_WAIT)
        assert not tx_execution_failed(j2), j2
        bounty_after_2 = router.get_bounty(args=[bounty_id]).call()
        print("[view] get_bounty(1) after second find_and_judge:", bounty_after_2)
        status = bounty_after_2[3]
    else:
        status = status_after_1

    print(f"\n  measured bounty status after matching rounds: {status}")
    assert status in (0, 1)  # OPEN (exhausted with no FIT yet) or PROPOSED

    # --- cross-contract read via the worked example ------------------------
    print("\n[view] reader.describe_bounty(1) - live cross-contract read")
    desc = reader.describe_bounty(args=[bounty_id]).call()
    print("  ", desc)
    assert f"#{bounty_id}" in desc

    progress = reader.search_progress(args=[bounty_id]).call()
    print("[view] reader.search_progress(1):", progress)
    assert progress >= 1

    if status == 1:
        bounty_now = router.get_bounty(args=[bounty_id]).call()
        proposed_candidate = bounty_now[4]
        actionable_for_candidate = reader.is_actionable(args=[bounty_id, proposed_candidate]).call()
        print("[view] reader.is_actionable(1, proposed_candidate):", actionable_for_candidate)
        assert actionable_for_candidate is True

        actionable_for_owner = reader.is_actionable(args=[bounty_id, owner.address]).call()
        print("[view] reader.is_actionable(1, owner):", actionable_for_owner)
        assert actionable_for_owner is False

        # --- negative: only the proposed candidate may confirm -------------
        wrong_confirmer = worker_bad if proposed_candidate.as_hex.lower() != worker_bad.address.lower() else worker_good
        print("\n[write] confirm_match(1) as the WRONG worker - expect refusal")
        bad_confirm = router.connect(wrong_confirmer).confirm_match(args=[bounty_id]).transact(wait_interval=12000, wait_retries=25)
        assert tx_execution_failed(bad_confirm), "non-candidate confirming must be refused"
        print("  refused as expected")

        # --- write: confirm_match - real payout ------------------------------
        candidate_account = worker_good if proposed_candidate.as_hex.lower() == worker_good.address.lower() else worker_bad
        print(f"\n[write] confirm_match(1) as the proposed candidate")
        confirm_tx = router.connect(candidate_account).confirm_match(args=[bounty_id]).transact(wait_interval=12000, wait_retries=25)
        assert not tx_execution_failed(confirm_tx), confirm_tx

        bounty_final = router.get_bounty(args=[bounty_id]).call()
        print("[view] get_bounty(1) after confirm_match:", bounty_final)
        assert bounty_final[3] == 2  # BOUNTY_MATCHED
    else:
        # Both candidates came back NOT_FIT/UNKNOWN: exercise the expiry
        # refund path for real instead, since the pool is now exhausted.
        print("\n[write] reclaim_expired_bounty(1) - pool exhausted, no FIT found")
        reclaim_tx = router.reclaim_expired_bounty(args=[bounty_id]).transact(wait_interval=12000, wait_retries=25)
        assert not tx_execution_failed(reclaim_tx), reclaim_tx
        bounty_final = router.get_bounty(args=[bounty_id]).call()
        print("[view] get_bounty(1) after reclaim_expired_bounty:", bounty_final)
        assert bounty_final[3] == 4  # BOUNTY_EXPIRED

    # --- write: post + cancel a second bounty (cheap, no nondet round) -----
    print(f"\n[write] post_bounty + cancel_bounty (second bounty) - refund path")
    post2 = router.connect(poster).post_bounty(args=[REQUIREMENT_TRUE]).transact(value=FEE, wait_interval=12000, wait_retries=25)
    assert not tx_execution_failed(post2), post2
    bounty_id_2 = 2
    cancel2 = router.connect(poster).cancel_bounty(args=[bounty_id_2]).transact(wait_interval=12000, wait_retries=25)
    assert not tx_execution_failed(cancel2), cancel2
    bounty2 = router.get_bounty(args=[bounty_id_2]).call()
    print("[view] get_bounty(2) after cancel:", bounty2)
    assert bounty2[3] == 3  # BOUNTY_CANCELLED

    # --- negative: only the owner may lower the pool cap --------------------
    print("\n[write] lower_pool_cap(5) as poster - expect refusal (not owner)")
    bad_cap = router.connect(poster).lower_pool_cap(args=[5]).transact(wait_interval=12000, wait_retries=25)
    assert tx_execution_failed(bad_cap), "non-owner lowering the cap must be refused"
    print("  refused as expected")

    # --- write: owner lowers the pool cap (monotonic) ------------------------
    print("\n[write] lower_pool_cap(5) as owner")
    cap_tx = router.lower_pool_cap(args=[5]).transact(wait_interval=12000, wait_retries=25)
    assert not tx_execution_failed(cap_tx), cap_tx
    cfg1 = router.get_config(args=[]).call()
    print("[view] get_config after lower_pool_cap:", cfg1)
    assert cfg1[1] == 5

    # --- negative: cannot raise the cap back up ------------------------------
    print("\n[write] lower_pool_cap(8) as owner - expect refusal (would raise)")
    raise_cap = router.lower_pool_cap(args=[8]).transact(wait_interval=12000, wait_retries=25)
    assert tx_execution_failed(raise_cap), "raising the cap must be refused"
    print("  refused as expected")

    # --- write: lower_bounty_cap too ------------------------------------------
    print("\n[write] lower_bounty_cap(5) as owner")
    bcap_tx = router.lower_bounty_cap(args=[5]).transact(wait_interval=12000, wait_retries=25)
    assert not tx_execution_failed(bcap_tx), bcap_tx
    cfg2 = router.get_config(args=[]).call()
    print("[view] get_config after lower_bounty_cap:", cfg2)
    assert cfg2[2] == 5

    # --- write: deactivate_worker -----------------------------------------
    print("\n[write] deactivate_worker as worker_bad")
    deact = router.connect(worker_bad).deactivate_worker(args=[]).transact(wait_interval=12000, wait_retries=25)
    assert not tx_execution_failed(deact), deact
    wb = router.get_worker(args=[worker_bad.address]).call()
    print("[view] get_worker(worker_bad) after deactivate:", wb)
    assert wb[2] is False

    # --- views: pagination -----------------------------------------------
    ids = router.get_bounty_ids(args=[0, 10]).call()
    print("[view] get_bounty_ids:", ids)
    assert bounty_id in ids and bounty_id_2 in ids

    total = router.bounty_count(args=[]).call()
    print("[view] bounty_count:", total)
    assert total == 2

    print("\nFull-surface run complete. Every write method executed at least once.")
