---
name: trader-pelosi
description: >-
  Unsupported US congressional-trades tracker. Congressional STOCK Act
  disclosures are not Indian insider or promoter filings, and no verified
  Indian replacement is implemented. Do not use this skill to track Indian
  disclosures.
argument-hint: ""
---

# trader-pelosi

This tool is **disabled for the NSE-only configuration**. The former
implementation read US House financial disclosure indexes and Congress PTR
documents. Those disclosures do not represent Indian insider or promoter
transactions, so the tool does not fetch, parse or display them.

An Indian replacement was not enabled: no official Indian source was verified
in this migration as a structured, auditable replacement for the existing
trade-by-trade PTR workflow. NSE corporate announcements are not represented
here as equivalent insider/promoter records. Do not substitute US Congress
disclosures or third-party trade trackers.

```bash
python3 "${CLAUDE_SKILL_DIR}/ptr.py" index
# Returns an unsupported message and exit code 2.
```

No disclosure data or state is fetched or written. Re-enable this function only
after a suitable official Indian source and its disclosure format are
independently verified.

Education and tooling, not financial advice.
