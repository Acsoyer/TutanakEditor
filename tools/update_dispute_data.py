"""DOCX_Guncelleme belgelerinden ticari uyuşmazlık verisini günceller.

Kaynak olarak Supabase dışa aktarım paketindeki arbsys-tum-veriler.json dosyasını
kullanır. Çıktıları yalnızca hedef v2 klasörüne yazar. Eşleşmesi belirsiz bir
belge varsa güncelleme yapmadan hata verir.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from docx import Document


ROOT = Path(__file__).resolve().parents[2]
V2_DIR = Path(__file__).resolve().parents[1]
DOCX_DIR = ROOT / "DOCX_Guncelleme"
BACKUP_DIR = DOCX_DIR / "arbsys-verileri_2026-08-31_16-30"
BACKUP_JSON = BACKUP_DIR / "arbsys-tum-veriler.json"
TITLE_FILE = DOCX_DIR / "VEYA ISIMLENDIRMELERI.txt"

FOLDER_TO_SUBTYPE = {
    "01) TTK md. 4 ve 5 (+)": "TTK md. 4 ve 5",
    "02) Ticari İşletme (+)": "Ticari İşletme",
    "03) Şirketler Yapısal Değişiklikler (+)": "Şirketler Yapısal Değişiklikler",
    "04) Kollektif (+)": "Kollektif Şirket",
    "05) Komandit (+)": "Komandit Şirket",
    "06) Anonim (+)": "Anonim Şirket",
    "07) Limited (+)": "Limited Şirket",
    "08) Kıymetli Evrak (+)": "Kıymetli Evrak",
    "09) Sigorta (+)": "Sigorta Uy",
}

NEW_SUBJECTS = {
    "A.Ş. Ortağının Hazırlık Dönemi Faizi Alacak Uyuşmazlığı": (
        "A.Ş. Ortağının Hazırlık Dönemi Faizi Alacak Uyuşmazlığı - TTK md. 510"
    ),
    "LTD Ortağının Hazırlık Dönemi Faizi Alacak Uyuşmazlığı": (
        "LTD Ortağının Hazırlık Dönemi Faizi Alacak Uyuşmazlığı - TTK md. 510"
    ),
}

RETIRED_DUPLICATE_RECORD_IDS = {"excel-row-172"}

DOCUMENT_SUBJECT_ALIASES = {
    "Pazarlamacılık Sözleşmesi": "Pazarlamacı - TBK md 448 vd.",
    "Haksız Rekabetten Kaynaklanan Uyuşmazlık": "Haksız Rekabet - TTK md. 56",
}


@dataclass
class ExtractedDoc:
    path: Path
    subtype: str
    file_key: str
    dispute_type_text: str
    negotiation_options: list[str]
    agreement_options: list[str]
    record: dict | None = None
    match_score: float = 0.0


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = value.replace("ı", "i")
    value = re.sub(r"\b04\s+anlasma\s+belgesi\b", " ", value)
    value = re.sub(r"[^a-z0-9çğıöşü]+", " ", value)
    return " ".join(value.split())


def split_alternatives(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"\n\s*VEYA\s*\n", text, flags=re.I)]


def extract_doc(path: Path, subtype: str) -> ExtractedDoc:
    document = Document(path)
    fields: dict[str, str] = {}
    for table in document.tables:
        for row in table.rows:
            if not row.cells:
                continue
            label = " ".join(row.cells[0].text.upper().split())
            value = row.cells[-1].text.strip()
            if "UYUŞMAZLIK TÜRÜ" in label:
                fields["type"] = value
            elif "UYUŞMAZLIK KONUSU" in label:
                fields["negotiation"] = value
            elif "VARILAN ANLAŞMA" in label:
                fields["agreement"] = value
    missing = {"type", "negotiation", "agreement"} - fields.keys()
    if missing:
        raise ValueError(f"{path}: eksik alanlar: {sorted(missing)}")
    return ExtractedDoc(
        path=path,
        subtype=subtype,
        file_key=normalize(path.stem),
        dispute_type_text=fields["type"],
        negotiation_options=split_alternatives(fields["negotiation"]),
        agreement_options=split_alternatives(fields["agreement"]),
    )


def load_documents() -> list[ExtractedDoc]:
    documents: list[ExtractedDoc] = []
    for folder_name, subtype in FOLDER_TO_SUBTYPE.items():
        folder = DOCX_DIR / folder_name
        paths = sorted(folder.glob("*.docx"), key=lambda p: p.name.casefold())
        documents.extend(extract_doc(path, subtype) for path in paths)
    return documents


def parse_title_blocks() -> list[tuple[str, list[str]]]:
    lines = [line.strip() for line in TITLE_FILE.read_text(encoding="utf-8-sig").splitlines()]
    blocks: list[tuple[str, list[str]]] = []
    section_names = {
        "VEYA ISIMLENDIRMELERI",
        "TTK MD. 4 VE 5",
        "TİCARİ İŞLETME",
        "ŞİRKETLER YAPISAL DEĞİŞİKLİKLER",
        "KOLLEKTİF ŞİRKET",
        "KOMANDİT ŞİRKET",
        "ANONİM ŞİRKET",
        "LİMİTED ŞİRKET",
        "KIYMETLİ EVRAK",
        "SİGORTA",
    }
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line or line in section_names or re.match(r"^\d+\)\s+", line):
            index += 1
            continue
        next_index = index + 1
        while next_index < len(lines) and not lines[next_index]:
            next_index += 1
        if next_index < len(lines) and re.match(r"^1\)\s+", lines[next_index]):
            titles: list[str] = []
            while next_index < len(lines):
                match = re.match(r"^\d+\)\s+(.*)$", lines[next_index])
                if not match:
                    break
                titles.append(match.group(1).strip())
                next_index += 1
            blocks.append((line, titles))
            index = next_index
        else:
            index += 1
    return blocks


def best_score(left: str, right: str) -> float:
    a, b = normalize(left), normalize(right)
    if a == b:
        return 1.0
    if a and (a in b or b in a):
        return 0.96
    return SequenceMatcher(None, a, b).ratio()


def match_documents(documents: list[ExtractedDoc], data: dict) -> list[dict]:
    commercial = [
        record
        for record in data["records"]
        if record.get("selection", {}).get("disputeType") == "Ticari Uyuşmazlıklar"
    ]
    by_subtype: dict[str, list[dict]] = defaultdict(list)
    for record in commercial:
        by_subtype[record["selection"]["subtype"]].append(record)

    used_ids: set[str] = set()
    audit: list[dict] = []
    for doc in documents:
        candidates = [record for record in by_subtype[doc.subtype] if record["id"] not in used_ids]
        alias_subject = next(
            (subject for marker, subject in DOCUMENT_SUBJECT_ALIASES.items() if marker in doc.path.stem),
            None,
        )
        alias_record = next(
            (record for record in candidates if record["selection"]["subject"] == alias_subject),
            None,
        )
        if alias_record is not None:
            doc.record = alias_record
            doc.match_score = 1.0
            used_ids.add(alias_record["id"])
            audit.append(
                {
                    "status": "matched-alias",
                    "file": str(doc.path),
                    "recordId": alias_record["id"],
                    "subject": alias_record["selection"]["subject"],
                    "score": 1.0,
                }
            )
            continue
        ranked = sorted(
            (
                (best_score(record["selection"]["subject"], doc.path.stem), record)
                for record in candidates
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        top_score, top_record = ranked[0] if ranked else (0.0, None)
        second_score = ranked[1][0] if len(ranked) > 1 else 0.0
        new_subject = next(
            (subject for marker, subject in NEW_SUBJECTS.items() if marker in doc.path.stem),
            None,
        )
        if new_subject and top_score < 0.82:
            doc.record = None
            doc.match_score = 1.0
            audit.append({"status": "new", "file": str(doc.path), "subject": new_subject})
            continue
        if top_record is None or top_score < 0.72 or top_score - second_score < 0.035:
            audit.append(
                {
                    "status": "ambiguous",
                    "file": str(doc.path),
                    "topScore": round(top_score, 4),
                    "secondScore": round(second_score, 4),
                    "topSubject": top_record["selection"]["subject"] if top_record else "",
                }
            )
            continue
        doc.record = top_record
        doc.match_score = top_score
        used_ids.add(top_record["id"])
        audit.append(
            {
                "status": "matched",
                "file": str(doc.path),
                "recordId": top_record["id"],
                "subject": top_record["selection"]["subject"],
                "score": round(top_score, 4),
            }
        )

    unmatched_records = [
        record for record in commercial if record["id"] not in used_ids
    ]
    ambiguous = [item for item in audit if item["status"] == "ambiguous"]
    if ambiguous or unmatched_records:
        problems = {
            "ambiguousDocuments": ambiguous,
            "unmatchedRecords": [
                {"id": record["id"], "subject": record["selection"]["subject"]}
                for record in unmatched_records
            ],
        }
        raise RuntimeError("Belge eşleştirmesi tamamlanamadı:\n" + json.dumps(problems, ensure_ascii=False, indent=2))
    return audit


def make_new_record(doc: ExtractedDoc, data: dict) -> dict:
    subject = next(subject for marker, subject in NEW_SUBJECTS.items() if marker in doc.path.stem)
    existing_ids = {record["id"] for record in data["records"]}
    base_id = "docx-update-" + "-".join(normalize(subject).split())
    record_id = base_id
    suffix = 2
    while record_id in existing_ids:
        record_id = f"{base_id}-{suffix}"
        suffix += 1
    return {
        "id": record_id,
        "selection": {
            "disputeType": "Ticari Uyuşmazlıklar",
            "subtype": doc.subtype,
            "subtypeIsPlaceholder": False,
            "subject": subject,
        },
        "templateValues": {
            "disputeType": doc.dispute_type_text,
            "negotiationOptions": doc.negotiation_options,
            "negotiationOptionTitles": [""] * len(doc.negotiation_options),
            "agreementOptions": doc.agreement_options,
            "agreementOptionTitles": [""] * len(doc.agreement_options),
        },
        "completeness": {
            "hasDocumentDisputeType": bool(doc.dispute_type_text),
            "hasNegotiationText": bool(doc.negotiation_options),
            "hasAgreementText": bool(doc.agreement_options),
            "canGenerateDocument": True,
            "missingDocumentColumns": [],
            "warningLabel": "",
        },
    }


def assign_title_blocks(documents: list[ExtractedDoc], blocks: list[tuple[str, list[str]]]) -> list[dict]:
    multi_docs = [
        doc
        for doc in documents
        if len(doc.negotiation_options) > 1 or len(doc.agreement_options) > 1
    ]
    used_docs: set[Path] = set()
    audit: list[dict] = []
    for heading, titles in blocks:
        ranked = sorted(
            ((best_score(heading, doc.path.stem), doc) for doc in multi_docs if doc.path not in used_docs),
            key=lambda item: item[0],
            reverse=True,
        )
        score, doc = ranked[0]
        second = ranked[1][0] if len(ranked) > 1 else 0.0
        if score < 0.72 or score - second < 0.03:
            raise RuntimeError(
                f"Başlık bloğu eşleşmedi: {heading!r}; en yakın={doc.path.name!r}; "
                f"puan={score:.3f}; ikinci={second:.3f}"
            )
        used_docs.add(doc.path)
        values = doc.record["templateValues"]
        neg_count = len(doc.negotiation_options)
        agr_count = len(doc.agreement_options)
        values["negotiationOptionTitles"] = (
            (titles[:neg_count] + [""] * neg_count)[:neg_count] if neg_count > 1 else [""] * neg_count
        )
        values["agreementOptionTitles"] = (
            (titles[:agr_count] + [""] * agr_count)[:agr_count] if agr_count > 1 else [""] * agr_count
        )
        audit.append(
            {
                "heading": heading,
                "file": str(doc.path),
                "titleCount": len(titles),
                "negotiationOptionCount": neg_count,
                "agreementOptionCount": agr_count,
                "score": round(score, 4),
            }
        )
    return audit


def rebuild_hierarchy(data: dict) -> None:
    record_map = {record["id"]: record for record in data["records"]}
    commercial_type = next(item for item in data["hierarchy"] if item["name"] == "Ticari Uyuşmazlıklar")
    known_ids = {
        subject["recordId"]
        for subtype in commercial_type["subtypes"]
        for subject in subtype["subjects"]
    }
    new_records = [
        record
        for record in data["records"]
        if record["selection"]["disputeType"] == "Ticari Uyuşmazlıklar" and record["id"] not in known_ids
    ]
    for record in new_records:
        subtype = next(
            item for item in commercial_type["subtypes"] if item["name"] == record["selection"]["subtype"]
        )
        subtype["subjects"].append(
            {
                "label": record["selection"]["subject"],
                "displayLabel": record["selection"]["subject"],
                "recordId": record["id"],
                "canGenerateDocument": True,
            }
        )
        subtype["subjects"].sort(key=lambda item: normalize(item["label"]))
    for item in data["hierarchy"]:
        for subtype in item["subtypes"]:
            for subject in subtype["subjects"]:
                record = record_map.get(subject["recordId"])
                if record:
                    subject["canGenerateDocument"] = record["completeness"]["canGenerateDocument"]
                    subject["displayLabel"] = record["selection"]["subject"] + record["completeness"].get("warningLabel", "")


def retire_known_duplicates(data: dict) -> list[dict]:
    retired = [
        record for record in data["records"] if record["id"] in RETIRED_DUPLICATE_RECORD_IDS
    ]
    data["records"] = [
        record for record in data["records"] if record["id"] not in RETIRED_DUPLICATE_RECORD_IDS
    ]
    for item in data["hierarchy"]:
        for subtype in item["subtypes"]:
            subtype["subjects"] = [
                subject
                for subject in subtype["subjects"]
                if subject["recordId"] not in RETIRED_DUPLICATE_RECORD_IDS
            ]
    return [
        {"recordId": record["id"], "subject": record["selection"]["subject"]}
        for record in retired
    ]


def recalculate_metadata(data: dict) -> None:
    records = data["records"]
    negotiation_counts = Counter(len(r["templateValues"].get("negotiationOptions", [])) for r in records)
    agreement_counts = Counter(len(r["templateValues"].get("agreementOptions", [])) for r in records)
    incomplete = [r for r in records if not r["completeness"].get("canGenerateDocument")]
    mismatch = [
        r
        for r in records
        if len(r["templateValues"].get("negotiationOptions", []))
        != len(r["templateValues"].get("agreementOptions", []))
    ]
    data["summary"].update(
        {
            "recordCount": len(records),
            "subjectCount": sum(
                len(subtype["subjects"])
                for item in data["hierarchy"]
                for subtype in item["subtypes"]
            ),
            "negotiationSeparatorCount": sum(max(0, count - 1) for count in negotiation_counts.elements()),
            "agreementSeparatorCount": sum(max(0, count - 1) for count in agreement_counts.elements()),
            "negotiationOptionCounts": {str(k): v for k, v in sorted(negotiation_counts.items())},
            "agreementOptionCounts": {str(k): v for k, v in sorted(agreement_counts.items())},
            "mismatchedAlternativeRowCount": len(mismatch),
            "incompleteDocumentRowCount": len(incomplete),
        }
    )
    data["source"] = {
        "fileName": "DOCX_Guncelleme (171 DOCX)",
        "sheetName": "",
        "usedRange": "",
        "sha256": "",
        "headers": data.get("source", {}).get("headers", []),
    }
    data["validation"]["mismatchedAlternativeRows"] = [
        {
            "recordId": r["id"],
            "negotiationOptions": len(r["templateValues"].get("negotiationOptions", [])),
            "agreementOptions": len(r["templateValues"].get("agreementOptions", [])),
        }
        for r in mismatch
    ]


def update_data(export_package: dict) -> tuple[dict, dict]:
    data = deepcopy(export_package["disputeData"])
    retired_duplicates = retire_known_duplicates(data)
    documents = load_documents()
    if len(documents) != 171:
        raise RuntimeError(f"171 DOCX bekleniyordu, {len(documents)} bulundu")
    match_audit = match_documents(documents, data)

    changes: list[dict] = []
    for doc in documents:
        is_new = doc.record is None
        if doc.record is None:
            doc.record = make_new_record(doc, data)
            data["records"].append(doc.record)
        values = doc.record["templateValues"]
        before = {
            "disputeType": values.get("disputeType", ""),
            "negotiationOptions": values.get("negotiationOptions", []),
            "agreementOptions": values.get("agreementOptions", []),
        }
        values["disputeType"] = doc.dispute_type_text
        values["negotiationOptions"] = doc.negotiation_options
        values["agreementOptions"] = doc.agreement_options
        values["negotiationOptionTitles"] = [""] * len(doc.negotiation_options)
        values["agreementOptionTitles"] = [""] * len(doc.agreement_options)
        doc.record["completeness"].update(
            {
                "hasDocumentDisputeType": True,
                "hasNegotiationText": bool(doc.negotiation_options),
                "hasAgreementText": bool(doc.agreement_options),
                "canGenerateDocument": True,
                "missingDocumentColumns": [],
                "warningLabel": "",
            }
        )
        changes.append(
            {
                "recordId": doc.record["id"],
                "subject": doc.record["selection"]["subject"],
                "file": str(doc.path),
                "isNew": is_new,
                "disputeTypeChanged": before["disputeType"] != doc.dispute_type_text,
                "negotiationChanged": before["negotiationOptions"] != doc.negotiation_options,
                "agreementChanged": before["agreementOptions"] != doc.agreement_options,
                "oldNegotiationCount": len(before["negotiationOptions"]),
                "newNegotiationCount": len(doc.negotiation_options),
                "oldAgreementCount": len(before["agreementOptions"]),
                "newAgreementCount": len(doc.agreement_options),
            }
        )

    title_audit = assign_title_blocks(documents, parse_title_blocks())
    rebuild_hierarchy(data)
    recalculate_metadata(data)
    report = {
        "documentCount": len(documents),
        "recordCount": len(data["records"]),
        "commercialRecordCount": sum(
            r["selection"]["disputeType"] == "Ticari Uyuşmazlıklar" for r in data["records"]
        ),
        "multiOptionDocumentCount": sum(
            len(doc.negotiation_options) > 1 or len(doc.agreement_options) > 1 for doc in documents
        ),
        "titleBlockCount": len(title_audit),
        "retiredDuplicates": retired_duplicates,
        "matchAudit": match_audit,
        "titleAudit": title_audit,
        "changes": changes,
    }
    return data, report


def write_outputs(export_package: dict, data: dict, report: dict) -> None:
    export_package = deepcopy(export_package)
    export_package["disputeData"] = data
    export_package["exportedAt"] = "2026-08-31T16:30:00+01:00"
    dispute_js = "window.ARBSYS_DISPUTE_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (V2_DIR / "arbsys-dispute-data.js").write_text(dispute_js, encoding="utf-8")
    (V2_DIR / "arbsys-tum-veriler-guncel.json").write_text(
        json.dumps(export_package, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (V2_DIR / "guncelleme-raporu.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (V2_DIR / "guncelleme-degisiklikleri.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "recordId", "subject", "isNew", "disputeTypeChanged", "negotiationChanged",
            "agreementChanged", "oldNegotiationCount", "newNegotiationCount",
            "oldAgreementCount", "newAgreementCount", "file",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: item.get(field, "") for field in fields} for item in report["changes"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Doğrulama geçerse v2 çıktılarını yazar")
    args = parser.parse_args()
    export_package = json.loads(BACKUP_JSON.read_text(encoding="utf-8-sig"))
    data, report = update_data(export_package)
    summary = {
        "documentCount": report["documentCount"],
        "recordCount": report["recordCount"],
        "commercialRecordCount": report["commercialRecordCount"],
        "multiOptionDocumentCount": report["multiOptionDocumentCount"],
        "titleBlockCount": report["titleBlockCount"],
        "changedNegotiation": sum(item["negotiationChanged"] for item in report["changes"]),
        "changedAgreement": sum(item["agreementChanged"] for item in report["changes"]),
        "newRecords": sum(item["isNew"] for item in report["changes"]),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.apply:
        write_outputs(export_package, data, report)


if __name__ == "__main__":
    main()
