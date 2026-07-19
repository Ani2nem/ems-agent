# Dev notes (cross-track)

Non-obvious findings and scoping decisions from work on this repo that
other agents/tracks are likely to hit too. Progressive-disclosure detail
for the one-line pointer in `CLAUDE.md`.

## Backend venv: use Python 3.12, not the default `python3`

On this machine, `python3` resolves to Homebrew's Python 3.14
(`/opt/homebrew/bin/python3`), which has **no prebuilt wheel for
`pydantic-core`**. `pip install -r requirements.txt` falls back to a
source build via `maturin`/`rustup`, which fails outright here (rustup is
running under x86_64 emulation on this aarch64 Mac and can't compile for
`aarch64-apple-darwin`: `error[E0463]: can't find crate for 'core'`).

CLAUDE.md's tech stack says Python 3.12 - that's not just a version
preference, it's required for this install to work at all on this box.
Create the backend venv with the Homebrew 3.12 interpreter explicitly:

```bash
cd backend
/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

If `python@3.12` isn't installed: `brew install python@3.12`. There was
no committed venv (`.venv/` is gitignored per-worktree), so every
fresh worktree/track needs this once.

## Scoping decision made without a check-in (track/epcr-nemsis-scope)

The NEMSIS export task brief said to check in if the NEMSIS element scope
grew "much larger than a focused subset." It did threaten to: real NEMSIS
codes procedures/history/symptoms against licensed SNOMED CT/ICD
vocabularies this repo has no access to. Rather than pause, the call made
was to **not** fabricate plausible-looking numeric codes for those
fields (that would just relocate the original overclaiming problem) and
instead fold them into the genuine free-text narrative element, which is
how real EMS charting already handles content that doesn't fit a coded
pick-list. Full rationale and the element-mapping table:
[`docs/nemsis-export.md`](./nemsis-export.md).

If another track also touches `ePCRChart`/NEMSIS territory, read that
file first - it explains which fields have a real coded NEMSIS home and
which don't.
