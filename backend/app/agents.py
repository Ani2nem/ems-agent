"""The four agent roles: audio parser, payer (denial + rulings), and defense.

Each role has a real path (Bedrock Converse) and a deterministic mock path.
``USE_BEDROCK=false`` takes the mock path everywhere, so the whole product flow
is exercisable locally and in tests with no AWS and no randomness.

The payer's ruling decisions are driven by a transparent "necessity score"
computed from the chart, so the mock is both realistic and predictable:

* re-review (round 1) is adversarial - it overturns only for a strongly
  documented, clearly emergent transport.
* the final ruling (round 2) is prompt-biased toward the provider, so it
  overturns anything with even modest justification; only genuinely weak charts
  fall through to human escalation.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from . import bedrock
from .config import settings

Decision = Literal["overturn", "uphold"]

_POLICY_DIR = Path(__file__).parent / "policies"
_POLICY_FILES = {"AETNA": "aetna_ambulance.txt", "MEDICARE": "cms_ambulance.txt"}

# Payer flips to provider on re-review only for a clearly emergent, well
# documented ALS transport; the final ruling has a much lower bar (biased).
_REREVIEW_OVERTURN_THRESHOLD = 5
_FINAL_OVERTURN_THRESHOLD = 2

_SEVERITY_KEYWORDS = (
    "high-speed",
    "significant",
    "ejection",
    "rollover",
    "intrusion",
    "unresponsive",
    "cardiac arrest",
    "hemorrhage",
    "penetrating",
)


@lru_cache(maxsize=None)
def load_policy(payer: str) -> str:
    return (_POLICY_DIR / _POLICY_FILES[payer]).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Necessity scoring (shared by mock rulings)
# --------------------------------------------------------------------------- #


def necessity_score(chart: dict) -> int:
    """A 0-7 measure of documented medical necessity for the billed service."""
    score = 0
    if chart.get("levelOfService") == "ALS":
        score += 2
    priority = (chart.get("transportPriority") or "").lower()
    if "1" in priority or "emergent" in priority:
        score += 1
    gcs = (chart.get("vitals") or {}).get("gcs")
    if gcs is not None and gcs < 15:
        score += 1
    if len(chart.get("interventions") or []) >= 2:
        score += 1
    moi = (chart.get("mechanismOfInjury") or "").lower()
    if any(k in moi for k in _SEVERITY_KEYWORDS):
        score += 1
    if chart.get("comorbidities"):
        score += 1
    return score


# --------------------------------------------------------------------------- #
# Audio parser
# --------------------------------------------------------------------------- #

_ALS_HINTS = (
    "als",
    "cardiac",
    "intubat",
    "epinephrine",
    "12-lead",
    "12 lead",
    "advanced airway",
    "iv access",
    "monitor",
)

# Accepts "58 year old", "58-year-old", "58yo", "58 y/o", "58 y.o." - a
# hyphen or space (or nothing) is allowed between the number and the word,
# and between the word's own parts.
_AGE_RE = re.compile(r"(\d{1,3})[\s-]*(?:yo\b|y/o|y\.o\.|years?[\s-]*old)")

_BP_RE = re.compile(r"\b(\d{2,3})\s*(?:/|over)\s*(\d{2,3})\b")
_HR_RE = re.compile(r"\b(?:heart rate|pulse|hr)\b\s*(?:of|is|:)?\s*(\d{2,3})\b")
_SPO2_KEYWORD_RE = re.compile(
    r"\b(?:spo2|o2\s*sat(?:uration)?s?|sat(?:uration)?s?)\b\s*(?:of|is|:)?\s*(\d{1,3})\s*%?"
)
_SPO2_PERCENT_RE = re.compile(r"\b(\d{1,3})\s*%")
_RR_RE = re.compile(r"\b(?:respiratory rate|resp rate|rr)\b\s*(?:of|is|:)?\s*(\d{1,3})\b")
_GCS_RE = re.compile(r"\b(?:gcs|glasgow coma(?:\s+scale)?)\b\s*(?:of|is|score|:)?\s*(\d{1,2})\b")

_MOI_KEYWORDS = (
    "mvc",
    "motor vehicle collision",
    "motor vehicle accident",
    "car accident",
    "collision",
    "rollover",
    "pedestrian struck",
    "pedestrian vs",
    "fall",
    "fell",
    "assault",
    "laceration",
    "gunshot",
    "gsw",
    "stabbing",
    "stab wound",
    "penetrating",
    "burn",
    "overdose",
    "syncope",
    "electrocution",
    "drowning",
)

_COMORBIDITY_PATTERNS = (
    (re.compile(r"\bdiabet\w*\b"), "diabetes"),
    (re.compile(r"\bcopd\b"), "COPD"),
    (re.compile(r"\b(?:chf|congestive heart failure)\b"), "CHF"),
    (re.compile(r"\b(?:hypertension|high blood pressure)\b"), "hypertension"),
    (re.compile(r"\b(?:renal failure|dialysis|esrd)\b"), "renal failure"),
    (re.compile(r"\basthma\b"), "asthma"),
    (re.compile(r"\b(?:afib|atrial fibrillation)\b"), "atrial fibrillation"),
    (re.compile(r"\b(?:cad|coronary artery disease)\b"), "coronary artery disease"),
    (re.compile(r"\b(?:seizure disorder|seizures?|epilepsy)\b"), "seizure disorder"),
)


def parse_chart(transcript: str) -> dict:
    if settings().use_bedrock:
        return _parse_chart_bedrock(transcript)
    return _mock_chart(transcript)


def _incident_id(transcript: str) -> str:
    digest = int(hashlib.md5(transcript.encode("utf-8")).hexdigest(), 16)
    return f"INC-2026-{digest % 100000:05d}"


def _extract_int(pattern: re.Pattern, t: str) -> int | None:
    match = pattern.search(t)
    return int(match.group(1)) if match else None


def _extract_bp(t: str) -> str | None:
    match = _BP_RE.search(t)
    return f"{match.group(1)}/{match.group(2)}" if match else None


def _extract_spo2(t: str) -> int | None:
    match = _SPO2_KEYWORD_RE.search(t) or _SPO2_PERCENT_RE.search(t)
    return int(match.group(1)) if match else None


def _extract_mechanism_of_injury(transcript: str) -> str:
    for clause in re.split(r"[.,;]", transcript):
        if any(k in clause.lower() for k in _MOI_KEYWORDS):
            cleaned = clause.strip()
            if cleaned:
                return cleaned
    return "Mechanism of injury not stated in dictation."


def _extract_comorbidities(t: str) -> list[str]:
    found = []
    for pattern, label in _COMORBIDITY_PATTERNS:
        if pattern.search(t) and label not in found:
            found.append(label)
    return found


def _mock_chart(transcript: str) -> dict:
    t = transcript.lower()
    payer = "MEDICARE" if "medicare" in t else "AETNA"
    als = any(h in t for h in _ALS_HINTS)
    level = "ALS" if als else "BLS"

    age_match = _AGE_RE.search(t)
    age = int(age_match.group(1)) if age_match else None
    sex = "F" if re.search(r"\b(female|woman|she|her)\b", t) else "M"

    emergent = any(k in t for k in ("priority 1", "emergent", "code 3", "lights and sirens"))
    priority = "Priority 1 (emergent)" if emergent or als else "Priority 2 (urgent)"

    interventions = []
    if any(k in t for k in ("iv", "iv access", "18-gauge", "16-gauge")):
        interventions.append("IV access")
    if "monitor" in t or "cardiac" in t or "12-lead" in t or "12 lead" in t:
        interventions.append("cardiac monitoring")
    if "oxygen" in t or "o2" in t or "spo2" in t:
        interventions.append("supplemental oxygen")
    if not interventions:
        interventions = ["patient assessment"]

    complaint = transcript.strip().split(".")[0].strip()
    if len(complaint) > 120:
        complaint = complaint[:117].rstrip() + "..."

    return {
        "incidentId": _incident_id(transcript),
        "patient": {"age": age, "sex": sex},
        "payer": payer,
        "chiefComplaint": complaint or "Unspecified complaint",
        "mechanismOfInjury": _extract_mechanism_of_injury(transcript),
        "vitals": {
            "gcs": _extract_int(_GCS_RE, t),
            "bp": _extract_bp(t),
            "hr": _extract_int(_HR_RE, t),
            "spo2": _extract_spo2(t),
            "rr": _extract_int(_RR_RE, t),
        },
        "interventions": interventions,
        "comorbidities": _extract_comorbidities(t),
        "levelOfService": level,
        "transportPriority": priority,
        "narrative": transcript.strip(),
    }


def _parse_chart_bedrock(transcript: str) -> dict:
    # incidentId is assigned by the backend (same deterministic hash as the
    # mock path), never requested from the model - asked to invent one, a
    # model that correctly follows "do not invent facts" returns null instead
    # of a string, which fails the chart's response schema.
    system = (
        "You are an EMS documentation specialist. Convert the paramedic's raw "
        "dictation into a structured NEMSIS-inspired ePCR chart. Respond with a "
        "single JSON object and nothing else, matching exactly these keys: "
        "patient{age,sex}, payer (AETNA or MEDICARE), chiefComplaint, "
        "mechanismOfInjury, vitals{gcs,bp,hr,spo2,rr}, interventions (array), "
        "comorbidities (array), levelOfService (BLS or ALS), transportPriority, "
        "narrative. Use null for unknown vitals. Do not invent facts."
    )
    raw = bedrock.converse(system, transcript, temperature=0.2)
    try:
        data = json.loads(_strip_code_fence(raw))
    except (ValueError, TypeError) as exc:
        repair_user = (
            f"{transcript}\n\n"
            f"Your previous response could not be parsed as JSON ({exc}). "
            "Respond again with ONLY a single valid JSON object - no markdown "
            "code fences, no commentary, no trailing text."
        )
        raw_retry = bedrock.converse(system, repair_user, temperature=0.2)
        try:
            data = json.loads(_strip_code_fence(raw_retry))
        except (ValueError, TypeError) as exc2:
            raise bedrock.BedrockError(
                f"could not parse chart JSON after retry: {exc2}"
            ) from exc2
    data["incidentId"] = _incident_id(transcript)
    return data


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


# --------------------------------------------------------------------------- #
# Payer agent - denial
# --------------------------------------------------------------------------- #


def _mock_reason_code(chart: dict) -> str:
    """ALS billed with thin ALS justification -> downcode; otherwise necessity."""
    if chart.get("levelOfService") == "ALS" and necessity_score(chart) < 4:
        return "DOWNGRADE"
    return "CO-50"


def _policy_excerpt_for_reason(policy: str, reason: str) -> str | None:
    """The policy's own line describing this adjudication/reason code, e.g.

    ``CO-50  Not medically necessary for the documented condition.`` Both
    policy files list codes this way, so a line-anchored match works for
    either payer without depending on section headers.
    """
    match = re.search(rf"^[ \t]*{re.escape(reason)}[ \t]+(.+)$", policy, re.MULTILINE)
    return match.group(1).strip() if match else None


def _policy_sentences(policy: str) -> list[str]:
    text = " ".join(line.strip() for line in policy.splitlines() if line.strip())
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _policy_basis_sentence(policy: str, chart: dict) -> str:
    """The policy sentence most relevant to the chart's billed level of service."""
    sentences = _policy_sentences(policy)
    if not sentences:
        return ""
    level = chart.get("levelOfService", "BLS")
    keywords = ["als"] if level == "ALS" else ["bls", "basic life support"]
    keywords.append("necess")
    for kw in keywords:
        for sentence in sentences:
            if kw in sentence.lower():
                return sentence
    return sentences[0]


def deny(chart: dict, payer: str, policy: str) -> tuple[str, str]:
    """Return ``(denial_content, reason_code)``."""
    if settings().use_bedrock:
        return _deny_bedrock(chart, payer, policy)
    reason = _mock_reason_code(chart)
    level = chart.get("levelOfService", "BLS")
    excerpt = _policy_excerpt_for_reason(policy, reason)
    citation = f' Per policy: "{reason} - {excerpt}"' if excerpt else ""
    if reason == "DOWNGRADE":
        content = (
            f"Claim adjusted under {reason}. Documentation supports medically "
            f"necessary transport but does not substantiate the {level} level of "
            "service billed; reimbursement is allowed at the BLS level. The "
            "reported condition and interventions do not clearly require an ALS "
            f"assessment or ALS intervention per policy.{citation}"
        )
    else:
        content = (
            f"Claim denied under {reason}: the submitted documentation does not "
            "establish that ambulance transport was medically necessary for the "
            "patient's condition, i.e., that any other means of transport would "
            "have endangered the patient. The narrative and vitals as recorded do "
            f"not substantiate the {level} level of service.{citation}"
        )
    return content, reason


def _deny_bedrock(chart: dict, payer: str, policy: str) -> tuple[str, str]:
    system = (
        f"You are a claims adjudicator for {payer}. Using ONLY the policy excerpt, "
        "issue a denial for this ambulance claim. Be specific and cite the policy. "
        "End with a final line exactly: 'REASON: <code>' where code is one of "
        "CO-50, CO-16, CO-11, DOWNGRADE."
    )
    user = f"POLICY:\n{policy}\n\nCHART:\n{json.dumps(chart)}"
    raw = bedrock.converse(system, user)
    reason = _extract_tag(raw, "REASON") or "CO-50"
    if reason not in {"CO-50", "CO-16", "CO-11", "DOWNGRADE"}:
        reason = "CO-50"
    content = _strip_tag_line(raw, "REASON")
    return content, reason


# --------------------------------------------------------------------------- #
# Defense agent - appeal
# --------------------------------------------------------------------------- #


def appeal(chart: dict, denial_content: str, policy: str, *, escalated: bool) -> str:
    if settings().use_bedrock:
        return _appeal_bedrock(chart, denial_content, policy, escalated=escalated)
    return _mock_appeal(chart, policy, escalated=escalated)


def _mock_appeal(chart: dict, policy: str, *, escalated: bool) -> str:
    level = chart.get("levelOfService", "BLS")
    priority = chart.get("transportPriority", "")
    gcs = (chart.get("vitals") or {}).get("gcs")
    interventions = chart.get("interventions") or []
    heading = "## Escalated Appeal" if escalated else "## Appeal"
    lines = [
        heading,
        "",
        f"We formally appeal the denial and assert that the {level} transport was "
        "medically necessary and correctly coded.",
        "",
        "**Cited facts**",
        f"- Dispatch: {priority}.",
    ]
    if gcs is not None and gcs < 15:
        lines.append(f"- Altered mental status documented (GCS {gcs}), an accepted necessity indicator.")
    if interventions:
        lines.append(f"- En-route interventions: {', '.join(interventions)}.")
    if chart.get("comorbidities"):
        lines.append(f"- Relevant comorbidities: {', '.join(chart['comorbidities'])}.")
    basis = _policy_basis_sentence(policy, chart)
    lines += [
        "",
        "**Policy basis**",
        f'- Policy: "{basis}" The contemporaneous record satisfies that standard.'
        if basis
        else "- The cited policy covers transport at the assessed level when the "
        "reported condition warrants an ALS assessment or intervention. The "
        "contemporaneous record satisfies that standard.",
    ]
    if escalated:
        lines.append(
            "- The prior re-review disregarded the documented acuity. We request a "
            "supervisory ruling consistent with policy."
        )
    return "\n".join(lines)


def _appeal_bedrock(chart: dict, denial_content: str, policy: str, *, escalated: bool) -> str:
    stance = (
        "This is a second-round escalation after the payer upheld the denial; "
        "argue firmly and request a supervisory overturn."
        if escalated
        else "Write a first-round appeal."
    )
    system = (
        "You are a defense appeals specialist for an EMS provider. Using ONLY the "
        "policy excerpt and the chart, write a persuasive, well-cited appeal in "
        f"Markdown rebutting the denial. {stance}"
    )
    user = (
        f"POLICY:\n{policy}\n\nCHART:\n{json.dumps(chart)}\n\nDENIAL:\n{denial_content}"
    )
    return bedrock.converse(system, user)


# --------------------------------------------------------------------------- #
# Payer agent - rulings
# --------------------------------------------------------------------------- #


def rule(chart: dict, appeal_content: str, policy: str, *, biased: bool) -> tuple[Decision, str]:
    """Re-review / final ruling. Returns ``(decision, ruling_content)``."""
    if settings().use_bedrock:
        return _rule_bedrock(chart, appeal_content, policy, biased=biased)
    return _mock_rule(chart, biased=biased)


def _mock_rule(chart: dict, *, biased: bool) -> tuple[Decision, str]:
    score = necessity_score(chart)
    threshold = _FINAL_OVERTURN_THRESHOLD if biased else _REREVIEW_OVERTURN_THRESHOLD
    decision: Decision = "overturn" if score >= threshold else "uphold"
    stage = "Supervisory Final Ruling" if biased else "Re-Review Determination"
    if decision == "overturn":
        content = (
            f"## {stage}\n\n**Decision: Overturned.** On review of the appeal and "
            "the contemporaneous documentation, the record substantiates medical "
            "necessity and the level of service billed. The prior denial is "
            "reversed and the claim is approved for payment."
        )
    else:
        content = (
            f"## {stage}\n\n**Decision: Upheld.** The appeal does not overcome the "
            "documentation gap: the record as submitted does not sufficiently "
            "establish that the billed level of service was medically necessary. "
            "The denial stands pending further documentation."
        )
    return decision, content


def _rule_bedrock(chart: dict, appeal_content: str, policy: str, *, biased: bool) -> tuple[Decision, str]:
    bias = (
        "As the final supervisory reviewer you should give the provider the "
        "benefit of the doubt and overturn unless the claim is clearly "
        "unsupported."
        if biased
        else "Apply the policy strictly and impartially."
    )
    system = (
        "You are a payer medical-review officer re-adjudicating an appealed "
        f"ambulance claim using ONLY the policy excerpt. {bias} Respond in "
        "Markdown, then end with a final line exactly: 'DECISION: OVERTURN' or "
        "'DECISION: UPHOLD'."
    )
    user = f"POLICY:\n{policy}\n\nCHART:\n{json.dumps(chart)}\n\nAPPEAL:\n{appeal_content}"
    raw = bedrock.converse(system, user)
    tag = (_extract_tag(raw, "DECISION") or "").lower()
    if tag not in {"overturn", "uphold"}:
        # Safe fallback matches each stage's bias.
        tag = "overturn" if biased else "uphold"
    return tag, _strip_tag_line(raw, "DECISION")  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Bedrock response parsing helpers
# --------------------------------------------------------------------------- #


def _extract_tag(text: str, tag: str) -> str | None:
    match = re.search(rf"\**\s*{tag}\s*:\s*\**\s*([A-Za-z0-9-]+)", text)
    return match.group(1) if match else None


def _strip_tag_line(text: str, tag: str) -> str:
    # Real model output doesn't always put the tag on the literal last line -
    # it sometimes bolds it (``**DECISION: OVERTURN**``) or appends a stray
    # trailing code fence afterward, neither of which the prompt asks for.
    # Match the tag's own line anywhere (MULTILINE) rather than anchoring to
    # end-of-string, and drop any leftover fence markers left behind.
    text = re.sub(rf"(?m)^\s*\**\s*{tag}\s*:.*$", "", text)
    text = re.sub(r"^\s*```\s*$", "", text, flags=re.MULTILINE)
    return text.strip()
