"""Structural FHIR R4 checks for a Bundle, mirroring what the organisers' validator says it checks
(docs/toolkit/docs/SCORING.md: resource types, ids, required elements, value sets, date / dateTime / instant syntax,
base64 attachments, every reference resolvable inside the Bundle).

Not a full R4 validator: it covers the resources and elements hospital exports use. It reports problem codes with the
JSON path where they occur, never the values (so its output can go to logs).
"""
from __future__ import annotations

import base64
import binascii
import re
import xml.etree.ElementTree as ET
from typing import Any

RESOURCE_TYPES = frozenset("""
Account AllergyIntolerance Appointment Basic Binary BodyStructure Bundle CarePlan CareTeam ClinicalImpression Claim
ClaimResponse Communication Composition Condition Consent Coverage Device DeviceRequest DiagnosticReport DocumentReference
Encounter EpisodeOfCare ExplanationOfBenefit FamilyMemberHistory Flag Goal Group HealthcareService ImagingStudy Immunization
List Location Media Medication MedicationAdministration MedicationDispense MedicationRequest MedicationStatement
Observation Organization Patient Person Practitioner PractitionerRole Procedure Provenance Questionnaire
QuestionnaireResponse RelatedPerson RiskAssessment ServiceRequest Specimen Task
""".split())

ID = re.compile(r"[A-Za-z0-9\-.]{1,64}")
DATE = re.compile(r"\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?")
DATETIME = re.compile(r"\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01])(T([01]\d|2[0-3]):[0-5]\d:([0-5]\d|60)(\.\d+)?"
                      r"(Z|[+-]((0\d|1[0-3]):[0-5]\d|14:00)))?)?)?")
INSTANT = re.compile(r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])T([01]\d|2[0-3]):[0-5]\d:([0-5]\d|60)(\.\d+)?"
                     r"(Z|[+-]((0\d|1[0-3]):[0-5]\d|14:00))")

# element name -> primitive type, for the date-like elements hospital exports use
DATE_ELEMENTS = {"birthDate": "date", "deceasedDate": "date"}
DATETIME_ELEMENTS = {"date", "recordedDate", "authoredOn", "effectiveDateTime", "performedDateTime", "onsetDateTime",
                     "abatementDateTime", "occurrenceDateTime", "start", "end", "deceasedDateTime", "valueDateTime",
                     "created", "whenHandedOver", "lastOccurrence", "assertedDate", "valueDate"}
INSTANT_ELEMENTS = {"lastUpdated", "timestamp", "issued", "recorded"}

VALUE_SETS = {
    ("Bundle", "type"): {"document", "message", "transaction", "transaction-response", "batch", "batch-response", "history",
                         "searchset", "collection", "subscription-notification"},
    ("Patient", "gender"): {"male", "female", "other", "unknown"},
    ("Practitioner", "gender"): {"male", "female", "other", "unknown"},
    ("RelatedPerson", "gender"): {"male", "female", "other", "unknown"},
    ("Encounter", "status"): {"planned", "arrived", "triaged", "in-progress", "onleave", "finished", "cancelled",
                              "entered-in-error", "unknown"},
    ("Observation", "status"): {"registered", "preliminary", "final", "amended", "corrected", "cancelled",
                                "entered-in-error", "unknown"},
    ("MedicationRequest", "status"): {"active", "on-hold", "cancelled", "completed", "entered-in-error", "stopped", "draft",
                                      "unknown"},
    ("MedicationRequest", "intent"): {"proposal", "plan", "order", "original-order", "reflex-order", "filler-order",
                                      "instance-order", "option"},
    ("Procedure", "status"): {"preparation", "in-progress", "not-done", "on-hold", "stopped", "completed",
                              "entered-in-error", "unknown"},
    ("Composition", "status"): {"preliminary", "final", "amended", "entered-in-error"},
    ("DocumentReference", "status"): {"current", "superseded", "entered-in-error"},
    ("DiagnosticReport", "status"): {"registered", "partial", "preliminary", "final", "amended", "corrected", "appended",
                                     "cancelled", "entered-in-error", "unknown"},
}
# FHIR element names are lowerCamelCase (a leading "_" carries a primitive's extensions); a renamed key such as
# "key_1a2b3c4d" is not an R4 element
ELEMENT = re.compile(r"_?[a-z][A-Za-z0-9]*")
TELECOM_SYSTEMS = {"phone", "fax", "email", "pager", "url", "sms", "other"}

REQUIRED = {
    "Bundle": ("type",),
    "Encounter": ("status", "class"),
    "Observation": ("status", "code"),
    "MedicationRequest": ("status", "intent", "subject"),
    "Procedure": ("status", "subject"),
    "Condition": ("subject",),
    "DocumentReference": ("status", "content"),
    "Composition": ("status", "type", "date", "author", "title"),
    "DiagnosticReport": ("status", "code"),
    "Immunization": ("status", "vaccineCode", "patient"),
}


def _collect_refs(node: Any, path: str, out: list) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "reference" and isinstance(v, str):
                out.append((path + ".reference", v))
            else:
                _collect_refs(v, f"{path}.{k}", out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _collect_refs(v, f"{path}[{i}]", out)


def _check_node(node: Any, path: str, rtype: str, problems: list) -> None:
    if isinstance(node, dict):
        if "contentType" in node and "data" in node:  # Attachment
            d = node.get("data")
            try:
                if not isinstance(d, str):
                    raise ValueError
                base64.b64decode(d, validate=True)
            except (binascii.Error, ValueError):
                problems.append(("attachment_not_base64", path + ".data"))
        if "system" in node and "value" in node and path.rsplit(".", 1)[-1].startswith("telecom"):
            if node["system"] not in TELECOM_SYSTEMS:
                problems.append(("telecom_system", path + ".system"))
        for k, v in node.items():
            p = f"{path}.{k}"
            if not ELEMENT.fullmatch(k):
                problems.append(("bad_element_name", p))
            if k == "div" and path.endswith(".text"):
                if not isinstance(v, str) or not v.lstrip().startswith("<div"):
                    problems.append(("narrative_not_div", p))
                else:
                    try:
                        ET.fromstring(v)
                    except ET.ParseError:
                        problems.append(("narrative_not_xhtml", p))
                continue
            if isinstance(v, str):
                if not v.strip():
                    problems.append(("empty_string", p))
                if k in DATE_ELEMENTS and not DATE.fullmatch(v):
                    problems.append(("bad_date", p))
                elif k in DATETIME_ELEMENTS and not DATETIME.fullmatch(v):
                    problems.append(("bad_datetime", p))
                elif k in INSTANT_ELEMENTS and not INSTANT.fullmatch(v):
                    problems.append(("bad_instant", p))
            _check_node(v, p, rtype, problems)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _check_node(v, f"{path}[{i}]", rtype, problems)


def _check_resource(res: Any, path: str, problems: list) -> None:
    if not isinstance(res, dict):
        problems.append(("resource_not_object", path))
        return
    rtype = res.get("resourceType")
    if rtype not in RESOURCE_TYPES:
        problems.append(("unknown_resource_type", path + ".resourceType"))
        return
    if "id" in res and not (isinstance(res["id"], str) and ID.fullmatch(res["id"])):
        problems.append(("bad_id", path + ".id"))
    for req in REQUIRED.get(rtype, ()):
        if not res.get(req) and not (req == "subject" and res.get("patient")):
            problems.append(("missing_required", f"{path}.{req}"))
    if rtype == "MedicationRequest" and not (res.get("medicationCodeableConcept") or res.get("medicationReference")):
        problems.append(("missing_required", path + ".medication[x]"))
    for (t, el), allowed in VALUE_SETS.items():
        if t == rtype and el in res and res[el] not in allowed:
            problems.append(("value_set", f"{path}.{el}"))
    if rtype == "DocumentReference":
        for i, c in enumerate(res.get("content") or []):
            if not isinstance(c, dict) or not c.get("attachment"):
                problems.append(("missing_required", f"{path}.content[{i}].attachment"))
    _check_node({k: v for k, v in res.items() if k not in ("resourceType", "id")}, path, rtype, problems)


def validate_bundle(bundle: Any) -> list[tuple[str, str]]:
    """Problems as (code, json path). An empty list means the Bundle passed every check here."""
    problems: list[tuple[str, str]] = []
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        return [("not_a_bundle", "")]
    if "id" in bundle and not (isinstance(bundle["id"], str) and ID.fullmatch(bundle["id"])):
        problems.append(("bad_id", "Bundle.id"))
    if bundle.get("type") not in VALUE_SETS[("Bundle", "type")]:
        problems.append(("value_set", "Bundle.type"))
    _check_node({k: v for k, v in bundle.items() if k not in ("entry", "resourceType", "id")}, "Bundle", "Bundle", problems)
    entries = bundle.get("entry") or []
    full_urls, typed_ids = set(), set()
    for i, e in enumerate(entries):
        p = f"Bundle.entry[{i}]"
        if not isinstance(e, dict):
            problems.append(("entry_not_object", p))
            continue
        res = e.get("resource")
        if isinstance(e.get("fullUrl"), str):
            full_urls.add(e["fullUrl"])
        if isinstance(res, dict) and isinstance(res.get("id"), str):
            typed_ids.add(f"{res.get('resourceType')}/{res['id']}")
        _check_resource(res, p + ".resource", problems)
    refs: list = []
    for i, e in enumerate(entries):
        if isinstance(e, dict):
            _collect_refs(e.get("resource"), f"Bundle.entry[{i}].resource", refs)
    for p, ref in refs:
        if ref.startswith("#"):
            continue
        if ref in full_urls or ref in typed_ids or any(u.endswith("/" + ref) for u in full_urls):
            continue
        problems.append(("unresolved_reference", p))
    return problems
