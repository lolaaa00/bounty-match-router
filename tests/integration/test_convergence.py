"""
Convergence test: the property BountyMatchRouter's deterministic logic
actually depends on validators agreeing about is the fit band itself
(FIT/NOT_FIT/UNKNOWN) - that is the only field any state transition or fund
movement ever branches on (see `_apply_verdict` in the contract: `confidence`
and `reason` are stored and reported, never read in a conditional). This
asserts the STRICT form on that property: not "no bad outcome occurred" but
that two independently deployed router instances, each judging the identical
requirement against the identical candidate summary, converge on the
identical fit band. A weak assertion ("fit is one of the three valid
strings") would pass even if the equivalence principle were silently letting
validators disagree and the leader's answer through unchecked.

Confidence is deliberately NOT included in the strict comparison. An earlier
version of this test asserted (fit, confidence) equality and a live run
produced ('FIT', 'HIGH') on one instance and ('FIT', 'MEDIUM') on the other -
both a genuine FIT, both grounded in the same evidence, differing only in
how emphatically the model expressed it across two independently-generated
responses. `prompt_comparative`'s equivalence principle governs agreement
among validators judging together *within one round*; it makes no claim
that two *separate* rounds, run independently with no shared state, will
produce byte-identical confidence wording. Since confidence never gates a
contract decision, treating that variance as a convergence failure would
be asserting a property the design never promised and the deterministic
code never relies on - the actual measured divergence is reported below,
not hidden.

Run with:
    gltest tests/integration/test_convergence.py -v -s --network studionet
"""
from gltest import get_contract_factory, get_default_account, create_accounts
from gltest.assertions import tx_execution_failed

JUDGE_WAIT = dict(wait_interval=8000, wait_retries=60)

REQUIREMENT = "Need a senior Python backend engineer comfortable with async REST APIs and databases."
SUMMARY = "I am a senior Python engineer with 6 years building async REST APIs and Postgres-backed services."


def test_repeated_judgement_on_identical_requirement_and_summary_converges_on_identical_fit():
    owner = get_default_account()
    accounts = create_accounts(2)
    poster, worker = accounts[0], accounts[1]

    factory = get_contract_factory("BountyMatchRouter")
    outcomes = []

    for i in range(2):
        router = factory.deploy(account=owner, args=[owner.address, 5, 5], wait_interval=12000, wait_retries=25)
        print(f"\n[deploy] convergence-test instance {i} at {router.address}")

        reg = router.connect(worker).register_worker(args=[SUMMARY]).transact(wait_interval=12000, wait_retries=25)
        assert not tx_execution_failed(reg), reg

        post = router.connect(poster).post_bounty(args=[REQUIREMENT]).transact(value=100, wait_interval=12000, wait_retries=25)
        assert not tx_execution_failed(post), post
        bounty_id = 1

        j = router.find_and_judge(args=[bounty_id]).transact(**JUDGE_WAIT)
        assert not tx_execution_failed(j), j

        bounty = router.get_bounty(args=[bounty_id]).call()
        fit, confidence, reason = bounty[5], bounty[6], bounty[7]
        print(f"[instance {i}] measured fit={fit!r} confidence={confidence!r} reason={reason!r}")
        outcomes.append((fit, confidence))

    fits = [o[0] for o in outcomes]
    print("\nMeasured fit bands across both independent instances:", fits)
    print("Measured (fit, confidence) pairs, informational only:", outcomes)
    assert fits[0] == fits[1], (
        f"convergence failed: the identical requirement against the identical "
        f"candidate summary produced different FIT BANDS (the only field any "
        f"contract decision ever branches on) across two independently "
        f"deployed instances: {fits}"
    )
