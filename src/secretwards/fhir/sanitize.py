"""Resource-aware sanitizing policy for a FHIR R4 Bundle.

A Bundle reaches detection as ONE record whose fields are its leaves, named by path
("entry[3].resource.name[0].family"). Detection alone cannot know which resource a leaf belongs to, so it removed
hospital names (Organization.name) and could miss an unseen patient name in Patient.name.family. This module decides,
per leaf, from the resource type and the element path:

  keep            no redaction (Organization / Practitioner / Location names and addresses, codings, URLs, statuses,
                  quantities, a patient's state / district / country, the doctor in Composition.author.display)
  patient_name    the whole leaf is the patient's name (Patient.name.*, Composition.subject.display, *.subject.display)
  relative_name   the whole leaf is a relative's name (Patient.contact.name.*, RelatedPerson.name.*)
  phone / email   telecom.value by its system
  mrn             a patient / encounter identifier value (feeds same-hospital linking, like any MRN)
  address         Patient.address.line / city / text
  pin             Patient.address.postalCode
  detect          everything else: free text, narrative, attachments, dates are left to the detectors

`apply_bundle_policy(units, spans)` turns those actions into spans in place: "keep" clears the leaf's spans, a forced
action replaces them with one whole-leaf span of the right type and role, "detect" leaves them alone. The contract
writer calls it once per Bundle record after detection and name memory, before linking, so the usual renderer then
embeds the pseudonym, shifts dates, generalizes PINs and aliases UUIDs exactly as for every other record.
Unknown resource types fall back to "detect" (the detectors still run), so new data is never left unprocessed.
"""
from __future__ import annotations

from typing import Mapping, MutableMapping, Optional, Sequence

import regex as re

from ..contracts import PIIType, Span, Unit

_LEAF = re.compile(r"^entry\[(\d+)\]\.resource\.(.+)$")
_IDX = re.compile(r"\[\d+\]")

# resources describing the care side (doctors, hospitals, places): their names and addresses are not patient data
_CARE_SIDE = frozenset({"Organization", "Practitioner", "PractitionerRole", "Location", "HealthcareService", "Device"})
# resources whose HumanName is the patient / a relative
_PATIENT_SIDE = frozenset({"Patient", "Person"})
_RELATIVE_SIDE = frozenset({"RelatedPerson"})

# element paths (indices removed) that never carry personal data in any resource
_ALWAYS_KEEP = re.compile(
    r"(?:^|\.)(?:resourceType|id|reference|status|intent|gender|use|system|code|version|unit|comparator|language|contentType|"
    r"url|profile|lastUpdated|versionId|div\.status)$|"
    r"(?:^|\.)coding\.display$|(?:^|\.)value(?:Quantity|Range|Ratio)\.|(?:^|\.)(?:value|low|high)\.value$|"
    r"(?:^|\.)(?:class|category|type|relationship|qualification\.code|clinicalStatus|verificationStatus)\.(?:coding\.)?(?:display|text)$")
_NAME = re.compile(r"^(?:name|contact\.name|alias)(?:\.(?:text|family|given|prefix|suffix))?$")


def _rtypes(fields: Mapping[str, str]) -> dict[int, str]:
    out = {}
    for k, v in fields.items():
        m = _LEAF.match(k)
        if m and m.group(2) == "resourceType":
            out[int(m.group(1))] = v
    return out


def is_bundle(fields: Mapping[str, str]) -> bool:
    return fields.get("resourceType") == "Bundle"


def _telecom_system(fields: Mapping[str, str], leaf: str) -> str:
    return (fields.get(leaf[: -len("value")] + "system") or "").strip().lower()


def leaf_action(rtype: Optional[str], el: str, leaf: str, fields: Mapping[str, str]) -> str:
    """Action for one leaf. `el` is the element path inside its resource with list indices removed ("name.given")."""
    if _ALWAYS_KEEP.search(el):
        return "keep"
    if rtype in _CARE_SIDE:
        # a doctor / hospital / place: names, addresses, qualifications stay; their phone numbers are not the patient's
        # either. Free-text notes inside them still go through detection.
        return "detect" if el.startswith(("text.div", "note.")) else "keep"
    if el in ("author.display", "performer.display", "requester.display", "participant.individual.display",
              "serviceProvider.display", "location.location.display", "custodian.display", "attester.party.display"):
        return "keep"  # references to doctors, hospitals and wards
    if el in ("subject.display", "patient.display", "beneficiary.display"):
        return "patient_name"
    if rtype in _PATIENT_SIDE or rtype in _RELATIVE_SIDE:
        m = _NAME.match(el)
        if m:
            if rtype in _RELATIVE_SIDE or el.startswith("contact."):
                return "relative_name"
            return "patient_name"
        if el == "telecom.value" or el == "contact.telecom.value":
            return "email" if _telecom_system(fields, leaf) == "email" else "phone"
        if el in ("identifier.value", "contact.identifier.value"):
            return "mrn"
        if el.startswith(("address.", "contact.address.")):
            last = el.rsplit(".", 1)[-1]
            if last in ("state", "country", "district"):
                return "keep"  # generalization levels, not identifiers
            if last == "postalCode":
                return "pin"
            if last in ("line", "city", "text"):
                return "address"
    if el == "identifier.value" and rtype in ("Encounter", "EpisodeOfCare", "Account", "Coverage", "Claim"):
        return "mrn"
    return "detect"


def bundle_actions(fields: Mapping[str, str]) -> dict[str, str]:
    """{field name: action} for every leaf of a Bundle record (fields as the contract reader names them)."""
    if not is_bundle(fields):
        return {}
    rtypes = _rtypes(fields)
    out = {}
    for leaf in fields:
        m = _LEAF.match(leaf)
        if m:
            el = _IDX.sub("", m.group(2))
            out[leaf] = leaf_action(rtypes.get(int(m.group(1))), el, leaf, fields)
        else:
            top = _IDX.sub("", leaf)
            # Bundle level: meta, identifier, timestamps, fullUrls
            out[leaf] = "keep" if _ALWAYS_KEEP.search(top) or top.startswith("entry.fullUrl") else "detect"
    return out


_FORCED = {
    "patient_name": (PIIType.NAME, "patient"),
    "relative_name": (PIIType.NAME, "relative"),
    "phone": (PIIType.PHONE, ""),
    "email": (PIIType.EMAIL, ""),
    "mrn": (PIIType.MRN, ""),
    "address": (PIIType.ADDRESS, ""),
    "pin": (PIIType.PINCODE, ""),
}


def apply_bundle_policy(fields: Mapping[str, str], units: Sequence[Unit], spans: MutableMapping) -> dict[str, int]:
    """Adjust `spans` ({field: [Span]}) of one Bundle record in place. Returns counts per action (no values)."""
    actions = bundle_actions(fields)
    counts: dict[str, int] = {}
    for u in units:
        act = actions.get(u.field)
        if act is None or act == "detect":
            continue
        counts[act] = counts.get(act, 0) + 1
        if act == "keep":
            spans[u.field] = []
            continue
        text = u.original
        a = len(text) - len(text.lstrip())
        b = len(text.rstrip())
        if b <= a:
            continue
        typ, role = _FORCED[act]
        spans[u.field] = [Span(u.doc_id, u.field, a, b, typ, "fhir_policy", 0.99, role)]
    return counts
