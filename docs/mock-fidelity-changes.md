# Mock-fidelity dehardcode (track/mock-fidelity-dehardcode)

Context for other parallel tracks: this branch fixed `backend/app/agents.py`'s
`_mock_chart()` / `deny()` / `_mock_appeal()` (the `USE_BEDROCK=false` path),
which were fabricating most of their output instead of extracting it from the
transcript.
Full rationale lives in `TASK_BRIEF.md` on that branch and in PR #6.
This doc only calls out things other tracks should know about.

## Frozen-contract change: `patient.age` is now nullable

`docs/api-contract.md`, `backend/app/models.py` (`Patient.age`), and
`frontend/src/types.ts` changed `age` from a required `number` to
`number | null`, matching the pattern the contract already used for every
`vitals` field.
The old mock silently defaulted to `55` when a transcript didn't state an
age; that's exactly the kind of fabrication this track was set up to
remove, so `null` had to become a legal value for `age` too.

**Why this matters to you:** if your branch also touches
`docs/api-contract.md`, `backend/app/models.py`, or
`frontend/src/types.ts`, expect a merge conflict or a silent regression
(a required-field assumption about `patient.age` that's no longer true)
once this lands on `main`.
Anywhere in the codebase that reads `chart.patient.age` (or
`chart["patient"]["age"]`) directly - display code, scoring, exports -
should null-check it.
`frontend/src/components/ChartPanel.tsx` shows the pattern used here
(`chart.patient.age ?? 'Unknown'`).

## For `track/bedrock-live-wiring`

`_parse_chart_bedrock`'s system prompt (`backend/app/agents.py`) says "Use
null for unknown vitals" but doesn't mention `patient.age` explicitly.
Now that the contract allows a null age, consider whether that prompt
should say so too, so the live-Bedrock path and the mock path agree on
what "unknown" produces.
This branch did not touch `_bedrock` functions or prompts at all, per its
own brief.

## For `track/epcr-nemsis-scope`

If you're expanding the `ePCRChart` shape, the extraction helpers added
here for the mock path (age/vitals/mechanismOfInjury/comorbidities regexes
in `backend/app/agents.py`, roughly lines 87-230) are a reference for the
"extract from transcript text, `null`/fallback when absent" pattern this
codebase now expects for every mock-parsed field - useful if new NEMSIS
fields need the same treatment instead of hardcoded mock values.

## Reusable additions (not contract changes, just new helpers)

`backend/app/agents.py` gained two small helpers usable by anything that
already has a loaded policy string and wants a real excerpt instead of
paraphrasing it:

- `_policy_excerpt_for_reason(policy, reason) -> str | None` - the
  policy's own line for a given adjudication/reason code (works for both
  `aetna_ambulance.txt` and `cms_ambulance.txt` since both list codes the
  same way: `CODE  description.`).
- `_policy_basis_sentence(policy, chart) -> str` - the policy sentence
  most relevant to the chart's billed level of service (ALS vs BLS).

Both are pure string functions with no I/O; see
`backend/tests/test_agents.py` (policy-citation section) for expected
behavior on both policy files.
