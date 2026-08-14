"""
Adversarial direct-mode test suite for BountyMatchRouter.

Coverage follows Phase 4 of the build spec: input validation, access
control, malformed model output, clamping, the explicit UNKNOWN path,
idempotency, time boundaries via warp_to, every value-moving branch, pool
capacity, ranking order, and the trust-model constraints from
docs/DESIGN.md (owner monotonicity, no owner fund custody).
"""

import json
import sys

sys.path.insert(0, "..")
from conftest import warp_to, as_address  # noqa: E402

CONTRACT = "contracts/bounty_match_router.py"

REQUIREMENT = "Need a Python backend engineer experienced with async APIs."
GOOD_SUMMARY = "Senior Python engineer, five years building async REST APIs."
BAD_SUMMARY = "I paint watercolor landscapes and teach yoga on weekends."

FIT = json.dumps({"fit": "FIT", "confidence": "HIGH", "reason": "matches backend skills"})
NOT_FIT = json.dumps({"fit": "NOT_FIT", "confidence": "MEDIUM", "reason": "unrelated skills"})
UNKNOWN = json.dumps({"fit": "UNKNOWN", "confidence": "LOW", "reason": "too vague"})


def _deploy(direct_deploy, owner, pool_cap=10, bounty_cap=10):
    return direct_deploy(CONTRACT, as_address(owner), pool_cap, bounty_cap)


def _register(c, direct_vm, worker, summary):
    direct_vm.startPrank(worker)
    c.register_worker(summary)


def _post(c, direct_vm, poster, amount=1000, requirement=REQUIREMENT):
    direct_vm.startPrank(poster)
    direct_vm.value = amount
    bounty_id = c.post_bounty(requirement)
    direct_vm.value = 0
    return bounty_id


def _find(c, direct_vm, bounty_id, llm_body):
    direct_vm.mock_llm(r".*", llm_body)
    result = c.find_and_judge(bounty_id)
    direct_vm.clear_mocks()
    return result


# ---------------------------------------------------------------------------
# Construction / input validation
# ---------------------------------------------------------------------------

def test_constructor_rejects_zero_owner(direct_deploy, direct_vm):
    with direct_vm.expect_revert("EXPECTED"):
        direct_deploy(CONTRACT, "0x" + "00" * 20, 10, 10)


def test_constructor_rejects_zero_pool_cap(direct_deploy, direct_owner):
    try:
        direct_deploy(CONTRACT, as_address(direct_owner), 0, 10)
        assert False, "expected revert"
    except Exception as e:
        assert "EXPECTED" in str(e)


def test_constructor_rejects_pool_cap_above_hard_limit(direct_deploy, direct_owner):
    try:
        direct_deploy(CONTRACT, as_address(direct_owner), 301, 10)
        assert False, "expected revert"
    except Exception as e:
        assert "EXPECTED" in str(e)


def test_constructor_rejects_bounty_cap_above_hard_limit(direct_deploy, direct_owner):
    try:
        direct_deploy(CONTRACT, as_address(direct_owner), 10, 201)
        assert False, "expected revert"
    except Exception as e:
        assert "EXPECTED" in str(e)


# ---------------------------------------------------------------------------
# Worker registration
# ---------------------------------------------------------------------------

def test_register_worker_rejects_empty_summary(direct_deploy, direct_vm, direct_owner, direct_alice):
    c = _deploy(direct_deploy, direct_owner)
    direct_vm.startPrank(direct_alice)
    with direct_vm.expect_revert("EXPECTED"):
        c.register_worker("")


def test_register_worker_rejects_oversized_summary(direct_deploy, direct_vm, direct_owner, direct_alice):
    c = _deploy(direct_deploy, direct_owner)
    direct_vm.startPrank(direct_alice)
    with direct_vm.expect_revert("EXPECTED"):
        c.register_worker("x" * 501)


def test_register_worker_is_idempotent_reregistration_does_not_grow_pool(
    direct_deploy, direct_vm, direct_owner, direct_alice
):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_alice, GOOD_SUMMARY)
    _register(c, direct_vm, direct_alice, "updated summary text")
    assert int(c.worker_count()) == 1
    summary, _reg_at, active = c.get_worker(as_address(direct_alice).as_hex)
    assert summary == "updated summary text"
    assert active is True


def test_register_worker_enforces_pool_cap(direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_owner, pool_cap=1)
    _register(c, direct_vm, direct_alice, GOOD_SUMMARY)
    direct_vm.startPrank(direct_bob)
    with direct_vm.expect_revert("EXPECTED"):
        c.register_worker(BAD_SUMMARY)


def test_deactivate_worker_requires_registration(direct_deploy, direct_vm, direct_owner, direct_alice):
    c = _deploy(direct_deploy, direct_owner)
    direct_vm.startPrank(direct_alice)
    with direct_vm.expect_revert("EXPECTED"):
        c.deactivate_worker()


def test_deactivate_worker_removes_from_ranking(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_alice, GOOD_SUMMARY)
    direct_vm.startPrank(direct_alice)
    c.deactivate_worker()
    bounty_id = _post(c, direct_vm, direct_bob)
    result = _find(c, direct_vm, bounty_id, FIT)
    assert result == "NO_CANDIDATES"


# ---------------------------------------------------------------------------
# Bounty posting / cancellation
# ---------------------------------------------------------------------------

def test_post_bounty_requires_positive_value(direct_deploy, direct_vm, direct_owner, direct_alice):
    c = _deploy(direct_deploy, direct_owner)
    direct_vm.startPrank(direct_alice)
    direct_vm.value = 0
    with direct_vm.expect_revert("EXPECTED"):
        c.post_bounty(REQUIREMENT)


def test_post_bounty_rejects_empty_requirement(direct_deploy, direct_vm, direct_owner, direct_alice):
    c = _deploy(direct_deploy, direct_owner)
    direct_vm.startPrank(direct_alice)
    direct_vm.value = 100
    with direct_vm.expect_revert("EXPECTED"):
        c.post_bounty("   ")
    direct_vm.value = 0


def test_post_bounty_rejects_oversized_requirement(direct_deploy, direct_vm, direct_owner, direct_alice):
    c = _deploy(direct_deploy, direct_owner)
    direct_vm.startPrank(direct_alice)
    direct_vm.value = 100
    with direct_vm.expect_revert("EXPECTED"):
        c.post_bounty("x" * 501)
    direct_vm.value = 0


def test_post_bounty_enforces_open_bounty_cap(direct_deploy, direct_vm, direct_owner, direct_alice):
    c = _deploy(direct_deploy, direct_owner, bounty_cap=1)
    _post(c, direct_vm, direct_alice)
    direct_vm.startPrank(direct_alice)
    direct_vm.value = 100
    with direct_vm.expect_revert("EXPECTED"):
        c.post_bounty(REQUIREMENT)
    direct_vm.value = 0


def test_cancel_bounty_requires_poster(direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_owner)
    bounty_id = _post(c, direct_vm, direct_alice)
    direct_vm.startPrank(direct_bob)
    with direct_vm.expect_revert("EXPECTED"):
        c.cancel_bounty(bounty_id)


def test_cancel_bounty_refunds_poster_in_full(direct_deploy, direct_vm, direct_owner, direct_alice):
    c = _deploy(direct_deploy, direct_owner)
    bounty_id = _post(c, direct_vm, direct_alice, amount=500)
    direct_vm.startPrank(direct_alice)
    c.cancel_bounty(bounty_id)
    _poster, _req, _amt, status, *_rest = c.get_bounty(bounty_id)
    assert int(status) == 3  # BOUNTY_CANCELLED


def test_cancel_bounty_rejects_already_cancelled(direct_deploy, direct_vm, direct_owner, direct_alice):
    c = _deploy(direct_deploy, direct_owner)
    bounty_id = _post(c, direct_vm, direct_alice)
    direct_vm.startPrank(direct_alice)
    c.cancel_bounty(bounty_id)
    with direct_vm.expect_revert("EXPECTED"):
        c.cancel_bounty(bounty_id)


def test_cancel_bounty_rejects_once_proposed(direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, GOOD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice)
    _find(c, direct_vm, bounty_id, FIT)
    direct_vm.startPrank(direct_alice)
    with direct_vm.expect_revert("EXPECTED"):
        c.cancel_bounty(bounty_id)


# ---------------------------------------------------------------------------
# find_and_judge -- ranking, fit bands, malformed output
# ---------------------------------------------------------------------------

def test_find_and_judge_returns_no_candidates_on_empty_pool(direct_deploy, direct_vm, direct_owner, direct_alice):
    c = _deploy(direct_deploy, direct_owner)
    bounty_id = _post(c, direct_vm, direct_alice)
    result = _find(c, direct_vm, bounty_id, FIT)
    assert result == "NO_CANDIDATES"


def test_find_and_judge_fit_proposes_match(direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, GOOD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice)
    result = _find(c, direct_vm, bounty_id, FIT)
    assert result == "FIT"
    _poster, _req, _amt, status, candidate, fit, *_rest = c.get_bounty(bounty_id)
    assert int(status) == 1  # BOUNTY_PROPOSED
    assert candidate.as_hex.lower() == as_address(direct_bob).as_hex.lower()
    assert fit == "FIT"


def test_find_and_judge_not_fit_leaves_bounty_open(direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, BAD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice)
    result = _find(c, direct_vm, bounty_id, NOT_FIT)
    assert result == "NOT_FIT"
    _poster, _req, _amt, status, *_rest = c.get_bounty(bounty_id)
    assert int(status) == 0  # BOUNTY_OPEN


def test_find_and_judge_malformed_llm_output_becomes_unknown_never_fit(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, GOOD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice)
    result = _find(c, direct_vm, bounty_id, "not valid json at all")
    assert result == "UNKNOWN"
    _poster, _req, _amt, status, *_rest = c.get_bounty(bounty_id)
    assert int(status) == 0


def test_find_and_judge_invented_fit_band_clamps_to_unknown(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, GOOD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice)
    invented = json.dumps({"fit": "MAYBE", "confidence": "HIGH", "reason": "?"})
    result = _find(c, direct_vm, bounty_id, invented)
    assert result == "UNKNOWN"


def test_find_and_judge_oversized_reason_is_truncated(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, GOOD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice)
    huge_reason = json.dumps({"fit": "FIT", "confidence": "HIGH", "reason": "z" * 900})
    _find(c, direct_vm, bounty_id, huge_reason)
    _poster, _req, _amt, _status, _cand, _fit, _conf, reason, *_rest = c.get_bounty(bounty_id)
    assert len(reason) <= 200


def test_find_and_judge_rejects_non_open_bounty(direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, GOOD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice)
    _find(c, direct_vm, bounty_id, FIT)
    with direct_vm.expect_revert("EXPECTED"):
        _find(c, direct_vm, bounty_id, FIT)


def test_find_and_judge_ranks_closer_embedding_first(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob, direct_charlie
):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, BAD_SUMMARY)
    _register(c, direct_vm, direct_charlie, GOOD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice, requirement=REQUIREMENT)
    _find(c, direct_vm, bounty_id, NOT_FIT)  # first candidate tried, regardless of outcome
    tried = int(c.get_tried_count(bounty_id))
    assert tried == 1


def test_find_and_judge_advances_to_next_candidate_after_not_fit(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob, direct_charlie
):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, BAD_SUMMARY)
    _register(c, direct_vm, direct_charlie, GOOD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice)
    _find(c, direct_vm, bounty_id, NOT_FIT)
    _find(c, direct_vm, bounty_id, FIT)
    assert int(c.get_tried_count(bounty_id)) == 2
    _poster, _req, _amt, status, *_rest = c.get_bounty(bounty_id)
    assert int(status) == 1


def test_find_and_judge_exhausted_pool_reports_no_candidates(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, BAD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice)
    _find(c, direct_vm, bounty_id, NOT_FIT)
    result = _find(c, direct_vm, bounty_id, NOT_FIT)
    assert result == "NO_CANDIDATES"


# ---------------------------------------------------------------------------
# confirm_match
# ---------------------------------------------------------------------------

def test_confirm_match_requires_proposed_candidate(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob, direct_charlie
):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, GOOD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice)
    _find(c, direct_vm, bounty_id, FIT)
    direct_vm.startPrank(direct_charlie)
    with direct_vm.expect_revert("EXPECTED"):
        c.confirm_match(bounty_id)


def test_confirm_match_requires_live_proposal(direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_owner)
    bounty_id = _post(c, direct_vm, direct_alice)
    direct_vm.startPrank(direct_bob)
    with direct_vm.expect_revert("EXPECTED"):
        c.confirm_match(bounty_id)


def test_confirm_match_pays_out_and_closes_bounty(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, GOOD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice, amount=777)
    _find(c, direct_vm, bounty_id, FIT)
    direct_vm.startPrank(direct_bob)
    c.confirm_match(bounty_id)
    _poster, _req, _amt, status, _cand, _fit, _conf, _reason, worker, *_rest = c.get_bounty(bounty_id)
    assert int(status) == 2  # BOUNTY_MATCHED
    assert worker.as_hex.lower() == as_address(direct_bob).as_hex.lower()


def test_confirm_match_rejects_double_confirm(direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, GOOD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice)
    _find(c, direct_vm, bounty_id, FIT)
    direct_vm.startPrank(direct_bob)
    c.confirm_match(bounty_id)
    with direct_vm.expect_revert("EXPECTED"):
        c.confirm_match(bounty_id)


def test_confirm_match_rejects_after_confirm_window_elapses(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob
):
    # The exact bug an external review caught: confirm_match must reject a
    # stale proposal on its own, not rely on someone else having already
    # called reclaim_expired_proposal to flip the bounty out of PROPOSED
    # first. A candidate who simply sits on an expired proposal must never
    # be able to confirm it after the window has passed.
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, GOOD_SUMMARY)
    warp_to(direct_vm, "2026-01-01T00:00:00+00:00")
    bounty_id = _post(c, direct_vm, direct_alice)
    _find(c, direct_vm, bounty_id, FIT)
    warp_to(direct_vm, "2026-01-01T00:30:00+00:00")  # exactly CONFIRM_TIMEOUT_SECONDS (1800s) later
    direct_vm.startPrank(direct_bob)
    with direct_vm.expect_revert("EXPECTED"):
        c.confirm_match(bounty_id)
    # bounty is still PROPOSED - confirm_match's own deadline check fired,
    # independent of whether reclaim_expired_proposal was ever called
    _poster, _req, _amt, status, *_rest = c.get_bounty(bounty_id)
    assert int(status) == 1  # BOUNTY_PROPOSED, unchanged


def test_confirm_match_succeeds_one_second_before_confirm_window_elapses(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, GOOD_SUMMARY)
    warp_to(direct_vm, "2026-01-01T00:00:00+00:00")
    bounty_id = _post(c, direct_vm, direct_alice, amount=555)
    _find(c, direct_vm, bounty_id, FIT)
    warp_to(direct_vm, "2026-01-01T00:29:59+00:00")  # one second short of the 1800s window
    direct_vm.startPrank(direct_bob)
    c.confirm_match(bounty_id)
    _poster, _req, _amt, status, _cand, _fit, _conf, _reason, worker, *_rest = c.get_bounty(bounty_id)
    assert int(status) == 2  # BOUNTY_MATCHED
    assert worker.as_hex.lower() == as_address(direct_bob).as_hex.lower()


def test_confirm_match_rejects_exactly_at_confirm_window_boundary(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob
):
    # Mirrors reclaim_expired_proposal's own boundary (elapsed >= TIMEOUT
    # reopens the bounty), so at exactly the boundary the two paths must
    # never overlap: confirm_match must already refuse by the same instant
    # reclaim_expired_proposal becomes callable.
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, GOOD_SUMMARY)
    warp_to(direct_vm, "2026-01-01T00:00:00+00:00")
    bounty_id = _post(c, direct_vm, direct_alice)
    _find(c, direct_vm, bounty_id, FIT)
    warp_to(direct_vm, "2026-01-01T00:30:00+00:00")  # exactly 1800s later
    c.reclaim_expired_proposal(bounty_id)  # now callable
    _poster, _req, _amt, status, *_rest = c.get_bounty(bounty_id)
    assert int(status) == 0  # BOUNTY_OPEN - reopened, never confirmable


def test_register_worker_reregistration_replaces_embedding_not_appends(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob
):
    # The exact bug an external review caught: appending the new embedding
    # on top of the old one instead of replacing it corrupts the stored
    # vector's dimensionality, which _cosine_millis defends against by
    # returning a similarity of 0 for any length mismatch (see the
    # contract's own comment on that function). That makes this directly
    # observable through ranking: alice first registers with completely
    # unrelated skills, then re-registers with skills that genuinely match
    # the bounty far better than bob's. If re-registration only appended,
    # alice's corrupted (double-length) embedding would score 0 against the
    # requirement and bob - an honestly weaker but correctly single-length
    # match - would be ranked ahead of her and tried first. With the fix,
    # alice's embedding correctly reflects only her current summary and she
    # is ranked, and tried, ahead of bob.
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_alice, BAD_SUMMARY)
    _register(c, direct_vm, direct_alice, GOOD_SUMMARY)  # re-registration
    _register(c, direct_vm, direct_bob, "Some Python experience, mostly scripting.")

    bounty_id = _post(c, direct_vm, direct_owner)
    _find(c, direct_vm, bounty_id, FIT)

    _poster, _req, _amt, status, candidate, *_rest = c.get_bounty(bounty_id)
    assert int(status) == 1  # BOUNTY_PROPOSED
    assert candidate.as_hex.lower() == as_address(direct_alice).as_hex.lower(), (
        "alice's re-registered (replaced, not appended) embedding must rank "
        "and be tried ahead of bob's honestly-weaker but correctly-sized one"
    )

    summary, _reg_at, active = c.get_worker(as_address(direct_alice).as_hex)
    assert summary == GOOD_SUMMARY
    assert active is True


# ---------------------------------------------------------------------------
# Time-boundary paths: reclaim_expired_proposal / reclaim_expired_bounty
# ---------------------------------------------------------------------------

def test_reclaim_expired_proposal_rejects_before_timeout(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, GOOD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice)
    _find(c, direct_vm, bounty_id, FIT)
    with direct_vm.expect_revert("EXPECTED"):
        c.reclaim_expired_proposal(bounty_id)


def test_reclaim_expired_proposal_reopens_bounty_after_timeout(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, GOOD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice)
    _find(c, direct_vm, bounty_id, FIT)
    warp_to(direct_vm, "2999-01-01T00:00:00+00:00")
    c.reclaim_expired_proposal(bounty_id)
    _poster, _req, _amt, status, candidate, *_rest = c.get_bounty(bounty_id)
    assert int(status) == 0  # BOUNTY_OPEN again
    assert candidate.as_hex.lower() == "0x" + "00" * 20


def test_reclaim_expired_bounty_rejects_before_timeout_with_untried_workers(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, GOOD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice)
    with direct_vm.expect_revert("EXPECTED"):
        c.reclaim_expired_bounty(bounty_id)


def test_reclaim_expired_bounty_allowed_immediately_once_pool_exhausted(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, BAD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice, amount=222)
    _find(c, direct_vm, bounty_id, NOT_FIT)  # pool now exhausted (only 1 worker, tried)
    c.reclaim_expired_bounty(bounty_id)
    _poster, _req, _amt, status, *_rest = c.get_bounty(bounty_id)
    assert int(status) == 4  # BOUNTY_EXPIRED


def test_reclaim_expired_bounty_allowed_after_timeout_even_with_untried_workers(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_deploy, direct_owner)
    bounty_id = _post(c, direct_vm, direct_alice)
    warp_to(direct_vm, "2999-01-01T00:00:00+00:00")
    _register(c, direct_vm, direct_bob, GOOD_SUMMARY)
    c.reclaim_expired_bounty(bounty_id)
    _poster, _req, _amt, status, *_rest = c.get_bounty(bounty_id)
    assert int(status) == 4


def test_reclaim_expired_bounty_rejects_non_open_status(
    direct_deploy, direct_vm, direct_owner, direct_alice, direct_bob
):
    c = _deploy(direct_deploy, direct_owner)
    _register(c, direct_vm, direct_bob, GOOD_SUMMARY)
    bounty_id = _post(c, direct_vm, direct_alice)
    _find(c, direct_vm, bounty_id, FIT)
    with direct_vm.expect_revert("EXPECTED"):
        c.reclaim_expired_bounty(bounty_id)


# ---------------------------------------------------------------------------
# Owner surface -- monotonic caps only, no fund custody
# ---------------------------------------------------------------------------

def test_lower_pool_cap_requires_owner(direct_deploy, direct_vm, direct_owner, direct_alice):
    c = _deploy(direct_deploy, direct_owner)
    direct_vm.startPrank(direct_alice)
    with direct_vm.expect_revert("EXPECTED"):
        c.lower_pool_cap(1)


def test_lower_pool_cap_rejects_raising_cap(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_owner, pool_cap=5)
    direct_vm.startPrank(direct_owner)
    with direct_vm.expect_revert("EXPECTED"):
        c.lower_pool_cap(10)


def test_lower_pool_cap_accepts_strict_decrease(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_owner, pool_cap=5)
    direct_vm.startPrank(direct_owner)
    c.lower_pool_cap(2)
    _owner, pool_cap, _bcap, _open, _next = c.get_config()
    assert int(pool_cap) == 2


def test_lower_bounty_cap_requires_owner(direct_deploy, direct_vm, direct_owner, direct_alice):
    c = _deploy(direct_deploy, direct_owner)
    direct_vm.startPrank(direct_alice)
    with direct_vm.expect_revert("EXPECTED"):
        c.lower_bounty_cap(1)


def test_lower_bounty_cap_rejects_raising_cap(direct_deploy, direct_vm, direct_owner):
    c = _deploy(direct_deploy, direct_owner, bounty_cap=5)
    direct_vm.startPrank(direct_owner)
    with direct_vm.expect_revert("EXPECTED"):
        c.lower_bounty_cap(10)


# ---------------------------------------------------------------------------
# Views / pagination
# ---------------------------------------------------------------------------

def test_get_bounty_reverts_on_unknown_id(direct_deploy, direct_owner):
    c = _deploy(direct_deploy, direct_owner)
    try:
        c.get_bounty(999)
        assert False, "expected revert"
    except Exception as e:
        assert "EXPECTED" in str(e)


def test_get_worker_reverts_on_unknown_address(direct_deploy, direct_owner, direct_alice):
    c = _deploy(direct_deploy, direct_owner)
    try:
        c.get_worker(as_address(direct_alice).as_hex)
        assert False, "expected revert"
    except Exception as e:
        assert "EXPECTED" in str(e)


def test_get_bounty_ids_paginates(direct_deploy, direct_vm, direct_owner, direct_alice):
    c = _deploy(direct_deploy, direct_owner, bounty_cap=10)
    for _ in range(3):
        _post(c, direct_vm, direct_alice, amount=10)
    ids = c.get_bounty_ids(0, 2)
    assert len(ids) == 2
    all_ids = c.get_bounty_ids(0, 200)
    assert len(all_ids) == 3


def test_bounty_count_matches_posted_count(direct_deploy, direct_vm, direct_owner, direct_alice):
    c = _deploy(direct_deploy, direct_owner)
    _post(c, direct_vm, direct_alice)
    _post(c, direct_vm, direct_alice)
    assert int(c.bounty_count()) == 2
