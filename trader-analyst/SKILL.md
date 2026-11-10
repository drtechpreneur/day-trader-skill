---
name: trader-analyst
description: >-
  Earnings Analyst (unsupported for NSE-only research). The former tool used
  US SEC EDGAR company facts and is disabled rather than showing US data for
  Indian-listed companies. Use only to explain this limitation.
argument-hint: "[NSE symbols]"
---

# trader-analyst

The automated earnings-analysis tool is currently **unsupported** for
NSE-listed companies. Its prior source was SEC EDGAR / US GAAP company facts;
that source cannot be treated as Indian issuer reporting. The tool now
refuses requests instead of looking up a coincidentally matching US ticker.

No Indian financial-reporting source has been verified here as a compatible,
structured replacement for the historical quarter-by-quarter metrics.
Issuer financial results may be available through exchange filings, but this
skill does not parse or normalize those reports. Review the issuer's NSE or
BSE filings directly; do not treat this tool as having fetched or analyzed
them.

```bash
python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE
# Returns an unsupported message and exit code 2.
```

No metrics file is written, and no US data is fetched or presented as Indian.
This functionality may be restored only after an Indian source and its
reported values are independently verified.

Education and tooling, not financial advice.
