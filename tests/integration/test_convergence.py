"""
Convergence test: the property BountyMatchRouter depends on validators
agreeing about is the fit band itself (FIT/NOT_FIT/UNKNOWN plus its
confidence band), grounded in one fixed, real requirement and candidate
summary pair. This asserts the STRICT form: not "no bad outcome occurred"
but that two independently deployed router instances, each judging the
identical requirement against the identical candidate summary, converge on
the identical fit artifact -- the same fit string AND the same confidence
band. A weak assertion ("fit is one of the three valid strings") would pass
even if the equivalence principle were silently letting validators disagree
and the leader's answer through unchecked. This is the strong form that
would actually catch that.

Run with:
    gltest tests/integration/test_convergence.py -v -s --network studionet
"""
from gltest import get_contract_factory, get_default_account, create_accounts
from gltest.assertions import tx_execution_failed

JUDGE_WAIT = dict(wait_interval=5000, wait_retries=90)

REQUIREMENT = "Need a senior Python backend engineer comfortable with async REST APIs and databases."
SUMMARY = "I am a senior Python engineer with 6 years building async REST APIs and Postgres-backed services."


def test_repeated_judgement_on_identical_requirement_and_summary_converges_on_identical_fit():
    owner = get_default_account()
    accounts = create_accounts(2)
    poster, worker = accounts[0], accounts[1]

    factory = get_contract_factory("BountyMatchRouter")
    outcomes = []

    for i in range(2):
        router = factory.deploy(account=owner, args=[owner.address, 5, 5])
        print(f"\n[deploy] convergence-test instance {i} at {router.address}")

        reg = router.connect(worker).register_worker(args=[SUMMARY]).transact()
        assert not tx_execution_failed(reg), reg

        post = router.connect(poster).post_bounty(args=[REQUIREMENT]).transact(value=100)
        assert not tx_execution_failed(post), post
        bounty_id = 1

        j = router.find_and_judge(args=[bounty_id]).transact(**JUDGE_WAIT)
        assert not tx_execution_failed(j), j

        bounty = router.get_bounty(args=[bounty_id]).call()
        artifact = (bounty[5], bounty[6])  # (proposed_fit, proposed_confidence)
        print(f"[instance {i}] measured artifact = {artifact}, reason = {bounty[7]!r}")
        outcomes.append(artifact)

    print("\nMeasured artifacts across both independent instances:", outcomes)
    assert outcomes[0] == outcomes[1], (
        f"convergence failed: the identical requirement against the identical "
        f"candidate summary produced different fit/confidence artifacts across "
        f"two independently deployed instances: {outcomes}"
    )
