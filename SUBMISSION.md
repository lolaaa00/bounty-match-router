# Submission

**Title:** BountyMatchRouter — Skill-Matching Escrow via Ranked Semantic Fit

**Description (986 chars, verified programmatically against
`SUBMISSION_DESCRIPTION.txt` via
`python3 -c "print(len(open(path).read().rstrip(chr(10))))"`):** see
`SUBMISSION_DESCRIPTION.txt` in this folder — the exact text submitted, kept
as its own file so the character count is independently reproducible.

## Evidence links

- **GitHub repo:** https://github.com/lolaaa00/bounty-match-router
  (placeholder — repo not yet pushed; push happens as a separate step)
- **StudioNet contract address:** pending — the StudioNet full-surface run
  found and fixed two real bugs (a `gltest` factory path issue and a
  missing `.view()` call in the worked example — see README's honest
  limits section), and the retry after both fixes was blocked by
  StudioNet's hourly rate limit (`retry_after_seconds: 3600`) before
  completing. An earlier attempt against this same contract logic already
  confirmed `find_and_judge` running a real consensus round and correctly
  returning `FIT`/`HIGH` for a genuinely matching skill summary. Next
  command once the hourly window resets:
  `gltest tests/integration/ -v -s --network studionet`, then
  `genlayer deploy --contract contracts/bounty_match_router.py`.
- **Explorer:** pending the deploy above —
  `https://explorer-studio.genlayer.com/address/<address>`
- **Studio import:** `https://studio.genlayer.com` (paste the address once
  deployed)

## Git hygiene

Verified with:

```bash
git log --format='%B' -- "intelligent contract/(bounty-match-router)" | grep -i "co-authored\|claude\|generated with"
```

No matches — no AI/agent attribution in any commit message.
