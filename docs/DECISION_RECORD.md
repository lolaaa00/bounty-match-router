# Decision Record — Fifth Intelligent Contract

## Phase 0: fresh grounding

Re-downloaded `research/sdk-api.txt` (6808 lines) and `research/docs-full.txt`
(19838 lines) from the canonical sources on 2026-08-04 and diffed byte-for-byte
against the copies already committed at the repo root. `diff` produced zero
output on both files — no material drift since the fourth contract's build.
No API surface, gotcha, or call-shape assumption below needed revision.

## Phase 1: candidates

Screened against gates:
- **A** — genuinely needs consensus/nondeterminism (not achievable with a
  plain deterministic contract).
- **B** — has a real, bounded failure/abstention path (never a fabricated
  positive result).
- **C** — structurally distinct from all four existing sibling contracts'
  core mechanism.
- **D** — nondet budget stays small (2-4 ops), fits one `resolve`-style call.
- **E** — funds (if any) have a defined resting place in every terminal
  state, no strandable escrow.
- **F** — not on the collision list (semantic change-detection on watched
  pages; multi-source corroboration/independence-clustering oracles).

| # | Candidate | Capability | Native value? | Verdict |
|---|---|---|---|---|
| 1 | Skill-match bounty router: embeddings rank a worker pool against a posted bounty spec, top-K get a semantic fit judgement, escrow pays the confirmed match | embeddings-for-ranking + escrow | yes | **PASS all gates — chosen** |
| 2 | Sandboxed code-review bounty: `spawn_sandbox` runs submitted code, validators judge whether the *trace/output content* matches a written spec | sandbox + semantic judgement | yes | passes gates, but heavier nondet budget (sandbox spawn + judge = already 2 ops before any retry path) and control-flow inside `spawn_sandbox` is the least-documented call shape in docs-full.txt — kept as strong runner-up |
| 3 | Upgrade-diff governance: proposal must ship a changelog; judge asks "does the diff match the changelog" before an upgrade pointer flips | governance-over-upgrades, semantic | no | passes C/D/E but no native value; contract #4 sibling already covers composition-heavy governance shape closely enough that reviewers could conflate it |
| 4 | Seeded-lottery grant selector: deterministic seed + judged eligibility criterion before payout | seeded randomness | yes | fails B: the "judgement" reduces to eligibility keyword matching, no genuine semantic risk — same trap noted twice in contract #4/#1 records |
| 5 | Résumé-to-role semantic router (variant of #1 but B2B intake form, no escrow) | embeddings-for-ranking | no | subset of #1, dropped for lacking native value |
| 6 | Grant application clustering + best-fit reviewer assignment | embeddings-for-routing | no | same shape as #1 without the escrow; folded into #1 |
| 7 | Sandbox-based CI gate paying a bug-bounty on a genuinely reproduced exploit trace | sandbox + semantic | yes | close cousin of #2; two sandbox ideas is redundant, dropped in favor of #2 as the sandbox representative |
| 8 | On-chain "spot the plagiarism" pairwise embeddings + judged originality score for content marketplace listings | embeddings, but similarity-threshold shaped | yes | fails F-adjacent: reduces to contract #2's dedup-gate shape (similarity + comparative judge over *pairs*) — explicitly the shape we must avoid rephrasing |
| 9 | Randomized validator-panel rotation as a primitive service other contracts subscribe to | seeded randomness + composition | no | mechanism reduces to deterministic modulo arithmetic once you remove the judgement; no real nondet content — fails A |
| 10 | Sandbox-executed puzzle-solution bounty (verify a program's *output value* only) | sandbox | yes | fails B — explicitly the "reduces to pass/fail" trap called out in the brief; no semantic content judged |
| 11 | Upgrade proposal marketplace: embeddings match proposals to reviewers by expertise, judge decides fit | embeddings-for-routing + governance | no | interesting hybrid but two capabilities is scope creep for one contract and no native value; #1 alone is cleaner |
| 12 | Freelance-task matching where embeddings pick the *closest semantic match* among competing bounty postings for a single worker profile (inverse direction of #1) | embeddings-for-ranking | yes | same mechanism as #1 with roles swapped; kept #1's framing (poster ranks workers) since it maps more naturally onto an escrow-and-confirm state machine |
| 13 | Deterministic-seed sortition among *pre-vetted* (judge-approved) candidates for a single payout slot | seeded randomness + semantic pre-filter | yes | interesting, but the semantic layer is a one-time gate rather than the ranking mechanism itself — closer in shape to contract #1's "judge then pay" than a new mechanism; dropped in favor of #1 |

13 candidates spanning embeddings-for-ranking, sandbox execution, governance-
over-upgrades, and seeded randomness — four distinct capabilities, five of
the thirteen involving native value.

## Chosen: Skill-Match Bounty Router (`bounty-match-router`)

**Mechanism.** A bounty poster deposits a reward and a short *requirement*
text plus a *skill vector* (embedding) for the job. Workers register profile
embeddings into a shared, capped pool. `find_and_judge` is a single write
call: it does one deterministic cosine-similarity ranking pass over the pool
(no nondet call — pure arithmetic) to pick the single closest-by-embedding
worker, then ONE nondet judgement asks whether that worker's *written skill
summary* (a short free-text field the worker supplies, not just their vector)
genuinely satisfies the bounty's *written requirement* — a semantic fit check,
not a similarity-threshold gate. If the judge says yes, the match is
proposed; the matched worker then confirms acceptance to receive the escrow.
If the judge says no (embedding-closest worker isn't actually qualified),
the contract advances to the next-closest candidate on a subsequent call
rather than paying out on cosine similarity alone.

**Why this is not a rephrasing of contract #2.** Contract #2 (payout-batch-
dedup) uses embeddings purely as a *duplicate/near-duplicate detector*:
cosine similarity against a *threshold* decides whether two submissions are
"too similar," and the judge's job is disambiguating genuine reword vs.
coincidental overlap between a PAIR. This contract uses embeddings for
*ranking/routing*: cosine similarity orders an entire pool of *distinct*
worker profiles against a job requirement to select ONE best candidate, and
the judge's job is deciding fit-for-purpose between a job spec and a
candidate — never comparing two submissions to each other, no threshold-gate
semantics anywhere in the design. There is no "is this a duplicate" question
in this contract at all.

**Why not contract #1 (web-fetch escrow):** no `gl.nondet.web.render` call
anywhere; evidence is caller-supplied text, not a live-fetched page.
**Why not contract #3 (photo-proof escrow):** no image judgement; no
`gl.nondet.exec_prompt(images=...)`.
**Why not contract #4 (factory + push-callback relay):** no factory, no
`gl.deploy_contract`, no deferred cross-contract emit. This is a single
self-contained instance a poster deploys or a marketplace router deploys
once; the worked example in `examples/` is a thin consumer that *reads*
match outcomes, not a sibling-spawning factory.

## Self-audit (per addendum)

- **Does the judged question reduce to a deterministic check in disguise?**
  No — "does this free-text skill summary satisfy this free-text
  requirement" is genuinely semantic; two different reasonable readers can
  disagree, which is exactly the class of question `prompt_comparative` is
  for. The deterministic part (cosine ranking) is explicitly NOT what decides
  payout — it only decides *candidate order*, and the judge can reject the
  top candidate.
- **Could a bad actor manufacture a favorable outcome by gaming the
  deterministic pre-filter?** A poster cannot force a match by inflating a
  worker's embedding similarity alone, because the judge still has to agree
  the worker's stated skills fit the stated requirement — an unrelated
  worker with a coincidentally close embedding is not automatically paid.
- **Is there a genuine "unknown" state, not just true/false?** Yes — `_judge`
  can return `UNKNOWN` (LLM/parse failure, empty requirement, ambiguous fit),
  which never auto-confirms a match; it advances the cursor to the next
  candidate instead of defaulting either direction.
- **Is native value ever strandable?** No — see docs/DESIGN.md "funds
  resting place" table: every terminal state (confirmed, expired-unmatched,
  cancelled-by-poster-before-match) has an explicit fund destination and a
  caller-triggered reclaim path with no owner discretion involved.
- **Any hidden collision with the two banned ideas?** No page-fetching, no
  change-detection, no independence-clustering across multiple sources.
