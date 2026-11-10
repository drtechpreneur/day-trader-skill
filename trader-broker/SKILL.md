---
name: trader-broker
description: >-
  NSE paper journal. Displays proposals that passed trader-risk, requires an
  explicit yes for one order, and records local simulation decisions and fills
  in INR. This tool is local-only and has no broker or exchange connection.
  Use for reviewing, journaling, flatten proposals, or paper fills.
argument-hint: "[order number]"
---

# trader-broker

This component is deliberately **not an order executor**. It is a local-only
paper journal and simulation helper for NSE cash-equity proposals. It has no
network calls, broker connectors, API keys, or live order route. It rejects
`paper: false` and any `broker` other than `local-paper`.

The workflow preserves two safety gates:

1. trader-risk must PASS the exact proposal today.
2. The user must explicitly approve that one local simulation.

Neither gate submits anything to a broker or exchange.

```bash
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show
python3 "${CLAUDE_SKILL_DIR}/ticket.py" approve --index 1 --reply "yes"
python3 "${CLAUDE_SKILL_DIR}/ticket.py" result --index 1 --status simulated \
  --filled-qty 8 --filled-price 2500
python3 "${CLAUDE_SKILL_DIR}/ticket.py" fill --symbol RELIANCE --side buy --qty 8 --price 2500
python3 "${CLAUDE_SKILL_DIR}/ticket.py" flatten --symbol RELIANCE
python3 "${CLAUDE_SKILL_DIR}/ticket.py" log
```

`show` renders the whole-share proposal, stop/target plan, and local-only
simulation data. `approve` stores the user's exact yes; it does not call an
order tool. `result --status simulated` records a paper simulation, optionally
adding an explicitly supplied simulated fill to `trader/portfolio.json`.
Otherwise use `fill` to record a simulated fill later. A flatten command
builds a local sell proposal from the paper portfolio. Check it with
trader-risk before approval.

Timestamps are IST (`+05:30`) and monetary amounts are INR (₹). The JSON
example `claude_desktop_config.example.json` is intentionally empty: do not
add an Alpaca, IBKR, or other live/paper broker connector for this component.

The local journal is not synchronized to a brokerage account. Review each
proposal and its share quantity, side, and limits before recording a decision.
Use an explicit `yes` only for the one proposal shown; broad or ambiguous
approval replies are refused.

Paper fills are editable local records and may not match exchange prices,
fees, taxes, or actual settlement. Keep a separate copy of the JSON journal
if you need a backup. Never use these records as a broker statement.

## Safety and limitations

- Never call a broker/exchange tool, connector, API, or live order route for this skill.
- Do not collect or store broker credentials.
- This journal does not fetch quotes, validate fills, or simulate exchange matching.
- A recorded fill is user-provided paper data, not a confirmed market execution.
- A stop is a plan value, not a guaranteed fill price.
- Education and tooling, not financial advice.
