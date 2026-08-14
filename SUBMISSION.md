# Submission

**Title:** BountyMatchRouter — Skill-Matching Escrow via Ranked Semantic Fit

**Description (1000 chars, verified programmatically against
`SUBMISSION_DESCRIPTION.txt` via
`python3 -c "print(len(open(path).read().rstrip(chr(10))))"`):** see
`SUBMISSION_DESCRIPTION.txt` in this folder — the exact text submitted, kept
as its own file so the character count is independently reproducible.

## Evidence links

- **GitHub repo:** https://github.com/lolaaa00/bounty-match-router
- **StudioNet contract address:** `0x2a0359Db286486f348A3028A43ee4dcfb6F269Cb`
  (redeployed after fixing the two lifecycle bugs an external review found —
  see README's "The honest limits" and `docs/DESIGN.md`'s "Two lifecycle
  bugs found in external review" for the full account) — every write method
  called against this exact address on live consensus, including a real
  `find_and_judge` round, a real `confirm_match` payout, and a real
  `lower_pool_cap` state change confirmed via a follow-up read.
- **Explorer:** https://explorer-studio.genlayer.com/address/0x2a0359Db286486f348A3028A43ee4dcfb6F269Cb
- **Studio import:** open `https://studio.genlayer.com` and import
  `0x2a0359Db286486f348A3028A43ee4dcfb6F269Cb`

## Git hygiene

Verified with:

```bash
git log --format='%B' -- "intelligent contract/(bounty-match-router)" | grep -i "co-authored\|claude\|generated with"
```

No matches — no AI/agent attribution in any commit message.
