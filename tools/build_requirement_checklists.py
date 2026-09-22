"""Build requirement_checklists.csv from the framework requirements workbook.

Each checklist element is one thing a requirement expects a report to
disclose. The analysis asks every model to mark each element as evidenced,
not evidenced or not applicable, and the app derives Covers / Partly /
Doesn't cover from those marks, which keeps verdicts consistent between runs.

Elements come from the workbook's Guidance column for TCFD, TNFD, OSFI and
TPT. Only generic guidance is used, because sector supplements do not apply to
every reporter. ESRS E1's guidance is long application text, so its elements
are the lettered items each ESRS E1 requirement already lists. SBTi's Guidance
column holds section headings rather than expectations, so SBTi and the
frameworks without guidance keep the model's overall judgement.

Run from the repository root:

    python tools/build_requirement_checklists.py

The CSV is meant to be reviewed and edited by the working party. Rerunning
this script overwrites any manual edits.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "ReportingFrameworks_v1.xlsx"
OUTPUT = ROOT / "requirement_checklists.csv"

GUIDANCE_FRAMEWORKS = ("TCFD", "TNFD", "OSFI", "TPT")
REQUIREMENT_TEXT_FRAMEWORKS = ("ESRS E1",)
COLUMNS = (
    "Framework",
    "Reference",
    "Requirement",
    "Element ID",
    "Element",
    "Counts towards Covers",
    "Source",
    "Note",
)

# Guidance that defines terms, points elsewhere or covers administration,
# rather than describing something a report can be checked for.
EXCLUDED_GUIDANCE_REFS = {
    "TNFD Strategy B13": "Pointer to the TNFD annex of example metrics",
    "TNFD Strategy D1": "Definition of priority locations",
    "TNFD Metrics and Targets C12": "Definition of which targets are in scope",
}
EXCLUDED_GUIDANCE_PREFIXES = {
    "The company is expected to implement the expectations": (
        "Implementation timetable"
    ),
    "The company may exercise discretion regarding the location": (
        "Where the disclosures may be published"
    ),
    "The company is expected to make its climate-related financial": (
        "Publication deadline, which cannot be checked from the report"
    ),
    "In-scope companys which are neither": (
        "Website link required only of certain companies"
    ),
    "The frequency for the disclosures": "Disclosure frequency",
    "The format for the disclosures": "Disclosure format",
}
# Guidance that stays on the checklist but does not decide Covers.
OPTIONAL_GUIDANCE_PREFIXES = {
    "Management should exercise discretion": (
        "Confidentiality discretion; only the statement of omissions can be "
        "checked"
    ),
    "The disclosures are not expected to be subject to independent": (
        "External assurance is not yet expected"
    ),
}
OPTIONAL_TPT_ITEMS = {
    ("TPT Strategy 2.4a", "d"): (
        "Describes how the information is prepared rather than what is "
        "disclosed"
    ),
}
# Wording that marks guidance as a suggestion rather than an expectation,
# and intro wording that marks a list as examples to fold into a single
# element rather than separate requirements.
OPTIONAL_TEXT_MARKERS = ("consider reporting", "recommended that")
OPTIONAL_INTRO_MARKERS = (*OPTIONAL_TEXT_MARKERS, "where possible", "may disclose")
OPTIONAL_TPT_ITEM = re.compile(r"^(?:may|need not)\b", re.IGNORECASE)
FOLD_INTRO_MARKERS = (
    "following areas",
    "such as",
    "may relate to",
    "may include",
    "for example",
)
FOLD_GUIDANCE_REFS = {
    # The bullets are acceptable reasons for omitting a metric.
    "TNFD Metrics and Targets A6",
    "TNFD Metrics and Targets B7",
}

BULLET = re.compile(r"^[-‒–—•▪◦·]\s*")
SUB_BULLET_CHARS = "•▪◦·"
TPT_ITEM = re.compile(r"^\(?\s*([a-z])\s*\)\.?\s*")
TPT_SUB_ITEM = re.compile(r"^(?:[ivx]+|\d+)\.\s+")
ESRS_ITEM = re.compile(r"^\((\d*[a-z])\)\s*")
ESRS_SUB_ITEM = re.compile(r"^\(([a-z])(?:i{1,3}|iv|vi{0,3}|ix|x)\)\s*")


def clean(text: object) -> str:
    """Collapse whitespace so text is stable across platforms and editors."""
    return " ".join(str(text).split())


def tidy(text: str) -> str:
    """Drop list punctuation left at the end of an item and capitalise it."""
    text = re.sub(r"(?:[;,]\s*and|[;,]|\s+and)$", "", text.strip()).strip()
    return text[:1].upper() + text[1:]


def join_sub_items(text: str, sub_items: list[str]) -> str:
    if not sub_items:
        return text
    items = "; ".join(tidy(item) for item in sub_items).replace(":;", ":")
    return f"{text.rstrip(':').rstrip()}: {items}"


def matches_prefix(text: str, prefixes: dict[str, str]) -> str | None:
    for prefix, note in prefixes.items():
        if text.startswith(prefix):
            return note
    return None


def guidance_row_elements(
    guidance: str,
    fold: bool = False,
) -> list[tuple[str, bool, str]]:
    """Split one bulleted guidance cell into (element, counts, note) items."""
    lines = [clean(line) for line in str(guidance).splitlines()]
    lines = [line for line in lines if line]
    sections: list[tuple[str, list[list]]] = []
    items: list[list] = []
    intro = None
    preamble: list[str] = []
    for line in lines:
        is_bullet = bool(BULLET.match(line))
        body = BULLET.sub("", line).strip()
        if line.endswith(":") and not is_bullet:
            if intro is not None:
                sections.append((intro, items))
            intro, items = line, []
            continue
        if intro is None:
            if is_bullet and preamble:
                # A list introduced without a colon, e.g. "should also disclose".
                intro, items = preamble[-1], []
            else:
                preamble.append(line)
                continue
        if (
            is_bullet
            and line[0] in SUB_BULLET_CHARS
            and items
            and items[-1][0].endswith(":")
        ):
            items[-1][1].append(body)
        elif (
            not is_bullet
            and items
            and not re.search(r"[.;:]$", items[-1][0])
            and body[:1].islower()
        ):
            # A wrapped line that continues the previous item.
            items[-1][0] = f"{items[-1][0]} {body}"
        else:
            items.append([body, []])
    if intro is not None:
        sections.append((intro, items))

    suggestion = "Suggested in the guidance rather than expected"
    if not sections or not any(section_items for _, section_items in sections):
        text = " ".join(lines)
        optional = any(
            marker in text.lower() for marker in OPTIONAL_TEXT_MARKERS
        )
        return [(tidy(text), not optional, suggestion if optional else "")]

    elements = []
    for section_intro, section_items in sections:
        lowered = section_intro.lower()
        optional = any(marker in lowered for marker in OPTIONAL_INTRO_MARKERS)
        note = suggestion if optional else ""
        texts = [join_sub_items(text, subs) for text, subs in section_items]
        if fold or any(marker in lowered for marker in FOLD_INTRO_MARKERS):
            elements.append(
                (tidy(join_sub_items(section_intro, texts)), not optional, note)
            )
        else:
            elements.extend((tidy(text), not optional, note) for text in texts)
    return elements


def tpt_elements(g_ref: str, guidance: str) -> list[tuple[str, bool, str]]:
    """Split TPT guidance into its lettered items, folding sub-items."""
    lines = [clean(line) for line in str(guidance).splitlines()]
    lines = [line for line in lines if line]
    intro, items = lines[0], []
    for line in lines[1:]:
        match = TPT_ITEM.match(line)
        if match:
            items.append([match.group(1), TPT_ITEM.sub("", line, count=1), []])
        elif items:
            items[-1][2].append(TPT_SUB_ITEM.sub("", line, count=1))
        else:
            intro = f"{intro} {line}"
    intro_optional = "may disclose" in intro.lower()
    elements = []
    for letter, text, sub_items in items:
        note = OPTIONAL_TPT_ITEMS.get((g_ref, letter), "")
        if not note and OPTIONAL_TPT_ITEM.match(text):
            note = "Optional in the TPT framework"
        if not note and intro_optional:
            note = "The TPT framework lists these as optional examples"
        elements.append((tidy(join_sub_items(text, sub_items)), not note, note))
    return elements


def esrs_elements(requirement: str) -> list[tuple[str, bool, str]]:
    """Return the lettered items an ESRS requirement lists, with sub-items."""
    intro_lines: list[str] = []
    items: list[list] = []
    for raw_line in str(requirement).splitlines():
        line = clean(raw_line)
        if not line:
            continue
        if ESRS_SUB_ITEM.match(line) and items:
            items[-1][1].append(ESRS_SUB_ITEM.sub("", line, count=1))
        elif ESRS_ITEM.match(line):
            items.append([ESRS_ITEM.sub("", line, count=1), []])
        elif items:
            items[-1][0] = f"{items[-1][0]} {line}"
        else:
            intro_lines.append(line)
    texts = [join_sub_items(text, subs) for text, subs in items]
    intro = " ".join(intro_lines)
    if texts and any(marker in intro.lower() for marker in FOLD_INTRO_MARKERS):
        # e.g. "policies address the following areas": one element, not five.
        return [(tidy(join_sub_items(intro, texts)), True, "")]
    return [(tidy(text), True, "") for text in texts]


def build_rows(workbook: pd.DataFrame) -> list[dict[str, str]]:
    rows = []
    checklists: dict[tuple[str, str], dict] = {}
    for _, row in workbook.iterrows():
        framework = clean(row.get("Framework", ""))
        requirement = clean(row.get("Recommendation", ""))
        if not requirement or requirement == "nan":
            continue
        key = (framework, requirement)
        reference = row.get("Reference")
        entry = checklists.setdefault(
            key,
            {
                "reference": "" if pd.isna(reference) else clean(reference),
                "elements": [],
            },
        )
        g_ref = "" if pd.isna(row.get("G_Ref")) else clean(row.get("G_Ref"))
        guidance = row.get("Guidance")
        if framework in GUIDANCE_FRAMEWORKS:
            if row.get("Scope") != "Generic" or pd.isna(guidance):
                continue
            if g_ref in EXCLUDED_GUIDANCE_REFS:
                continue
            guidance_text = clean(guidance)
            if matches_prefix(guidance_text, EXCLUDED_GUIDANCE_PREFIXES):
                continue
            if framework == "TPT":
                elements = tpt_elements(g_ref, guidance)
            else:
                elements = guidance_row_elements(
                    guidance, fold=g_ref in FOLD_GUIDANCE_REFS
                )
            optional_note = matches_prefix(
                guidance_text, OPTIONAL_GUIDANCE_PREFIXES
            )
            if optional_note:
                elements = [(text, False, optional_note) for text, _, _ in elements]
            source = g_ref or f"{framework} guidance"
            entry["elements"].extend(
                (text, counts, source, note) for text, counts, note in elements
            )
        elif framework in REQUIREMENT_TEXT_FRAMEWORKS and not entry["elements"]:
            entry["elements"].extend(
                (text, counts, "Requirement text", note)
                for text, counts, note in esrs_elements(
                    row.get("Recommendation", "")
                )
            )

    for (framework, requirement), entry in checklists.items():
        for index, (text, counts, source, note) in enumerate(
            entry["elements"], start=1
        ):
            rows.append(
                {
                    "Framework": framework,
                    "Reference": entry["reference"],
                    "Requirement": requirement,
                    "Element ID": f"E{index}",
                    "Element": text,
                    "Counts towards Covers": "Yes" if counts else "No",
                    "Source": source,
                    "Note": note,
                }
            )
    return rows


def main() -> None:
    workbook = pd.read_excel(WORKBOOK, engine="openpyxl")
    rows = build_rows(workbook)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    requirements = {(row["Framework"], row["Requirement"]) for row in rows}
    print(
        f"Wrote {len(rows)} elements for {len(requirements)} requirements "
        f"to {OUTPUT.name}"
    )


if __name__ == "__main__":
    main()
