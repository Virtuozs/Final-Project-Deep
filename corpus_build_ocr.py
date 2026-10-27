"""Ayat-level corpus builder driven by ocr_layout_extract.py's output.

Run ocr_layout_extract.py over raw_data/ first (without --combined-only --
this needs the per-page JSON):
    uv run python ocr_layout_extract.py raw_data --out outputs_layout --no-images

Usage:
    uv run python corpus_build_ocr.py
"""
from __future__ import annotations

import json
import pathlib
import re
from collections import Counter

from law_text_utils import LAWS, TRIVIAL, digit_class, find_pdf, heading_re, tidy

OUT = pathlib.Path("corpus-ocr.jsonl")
LAYOUT_DIR = pathlib.Path("outputs_layout")

SOURCE_URL = {
    "UU 14/2008": "https://peraturan.bpk.go.id/Details/39047/Uu-No-14-Tahun-2008",
    "PP 61/2010": "https://peraturan.bpk.go.id/Details/5084/pp-no-61-tahun-2010",
    "UU 25/2009": "https://peraturan.bpk.go.id/Details/38748/uu-no-25-tahun-2009",
    "UU 27/2022": "https://peraturan.bpk.go.id/Details/229798/UU-No-27-Tahun-2022",
}

# ocr_layout_extract.py's layout labels (PP-DocLayoutV2) that are running
# headers/footers/page furniture rather than law content.
NOISE_LABELS = {
    "header", "footer", "header_image", "footer_image", "number",
    "footnote", "vision_footnote", "image", "figure", "chart", "seal",
    "formula_number",
}

AYAT_OPEN = r"[\(lI|]"
AYAT_CLOSE = r"[\)lI|1]"


def ayat_re(n):
    """Matches an ayat marker ("(1)") either followed by content on the same
    line (the usual case) OR standing entirely alone on its own OCR line --
    seen when a narrow marker gets detected as its own short text row,
    separate from the sentence that follows it on the next line."""
    body = "".join(digit_class(d) for d in str(n))
    pattern = f"(?:{AYAT_OPEN}{body}{AYAT_CLOSE}?|{body}{AYAT_CLOSE})"
    return re.compile(r"^\s*" + pattern + r"(?:\s+\S.*)?$")


def ayat_label_re(n):
    """The Penjelasan section marks its ayat sub-headings as a standalone
    "Ayat (N)" line (the word spelled out), not body text's bare "(N)" --
    seen as its own short line/block, e.g. 'Ayat (1)', 'Ayat (2)'."""
    body = "".join(digit_class(d) for d in str(n))
    return re.compile(r"^\s*Ayat\s*" + AYAT_OPEN + body + AYAT_CLOSE + r"?\s*$", re.I)


BAB_RE = re.compile(r"^\s*BAB\s*[IVXLCDM0-9]+\b", re.I)  # \s* not \s+: OCR sometimes drops the space ("BABI")
BAGIAN_RE = re.compile(r"^\s*Bagian\s+\w+\b", re.I)
PARAGRAF_RE = re.compile(r"^\s*Paragraf\s+\w+\b", re.I)
# \b at the end matters: without it this also matches inside "penjelasannya" (a
# normal word, "its explanation"), which otherwise starts with "penjelasan".
PENJELASAN_RE = re.compile(r"PENJ\w{1,3}[A-Z,]{0,2}ASAN\b", re.I)
PASAL_DEMI_PASAL_RE = re.compile(r"PASAL\s*DEMI\s*PASAL", re.I)


def _looks_like_pasal_heading(text: str) -> bool:
    return bool(re.match(r"^\s*Pas[a-zA-Z0-9]{0,2}\s*[0-9OolIlZSTB|]+\s*$", text.strip()))


def _looks_like_section_heading(text: str) -> bool:
    t = text.strip()
    return bool(BAB_RE.match(t) or BAGIAN_RE.match(t) or PARAGRAF_RE.match(t))


def load_pages(doc_dir: pathlib.Path) -> list[dict]:
    """outputs_layout/<stem>/page-N/page-N.json, in page order."""
    pages = []
    i = 0
    while True:
        p = doc_dir / f"page-{i}" / f"page-{i}.json"
        if not p.exists():
            break
        data = json.loads(p.read_text(encoding="utf-8"))
        data["page_index"] = i
        pages.append(data)
        i += 1
    if not pages:
        raise FileNotFoundError(
            f"no page JSON under {doc_dir} -- run ocr_layout_extract.py on raw_data/ first "
            "(without --combined-only, since this builder needs the per-page JSON)"
        )
    return pages


def flatten_lines(pages: list[dict]) -> list[dict]:
    """One entry per OCR line (not per merged block), in reading order, with
    noise-labeled blocks dropped."""
    flat = []
    for page in pages:
        for blk in page.get("blocks", []):
            if blk.get("label") in NOISE_LABELS:
                continue
            for ln in blk.get("lines", []):
                text = (ln.get("text") or "").strip()
                if text:
                    flat.append({"text": text, "page_index": page["page_index"], "confidence": ln.get("confidence")})
        for ln in page.get("unassigned_lines", []):
            text = (ln.get("text") or "").strip()
            if text:
                flat.append({"text": text, "page_index": page["page_index"], "confidence": ln.get("confidence")})
    return flat


def drop_preamble(lines: list[dict]) -> list[dict]:
    """Everything before the first BAB heading is boilerplate (title block,
    Menimbang/Mengingat, "Dengan Rahmat Tuhan..."), not law content."""
    idx = next((i for i, ln in enumerate(lines) if BAB_RE.match(ln["text"])), None)
    return lines[idx:] if idx is not None else lines


def split_sections(lines: list[dict]) -> tuple[list[dict], list[dict]]:
    """body = before the PENJELASAN heading; elucidation = after 'PASAL DEMI PASAL'."""
    idx = next((i for i, ln in enumerate(lines) if PENJELASAN_RE.search(ln["text"])), None)
    if idx is None:
        return lines, []
    body, pen = lines[:idx], lines[idx:]
    j = next((i for i, ln in enumerate(pen) if PASAL_DEMI_PASAL_RE.search(ln["text"])), 0)
    return body, pen[j + 1:]


def parse_pasal_ayat(lines: list[dict], max_skip: int = 2, bare_ok: bool = False, is_explanation: bool = False) -> dict[int, dict]:
    """Single pass over a line stream (body or elucidation -- same shape in
    both): groups lines into {pasal_n: {"bab_number", "bab_title", "ayat": {ayat_n: [lines...]}}}.
    """
    pasal_data: dict[int, dict] = {}
    cur_pasal = None
    cur_ayat = 0
    cur_bab_number = cur_bab_title = None
    next_pasal_n = 1
    next_ayat_n = 1

    i, n = 0, len(lines)
    while i < n:
        text = lines[i]["text"].strip()

        if _looks_like_section_heading(text):
            if BAB_RE.match(text):
                cur_bab_number, cur_bab_title = text, None
            i += 1
            nxt = lines[i]["text"].strip() if i < n else ""
            if nxt and len(nxt) < 80 and not _looks_like_section_heading(nxt) and not _looks_like_pasal_heading(nxt):
                if BAB_RE.match(text):
                    cur_bab_title = nxt
                i += 1
            continue

        hit = next((k for k in range(next_pasal_n, next_pasal_n + max_skip + 1) if heading_re(k, bare_ok).match(text)), None)
        if hit is not None:
            cur_pasal, next_pasal_n = hit, hit + 1
            cur_ayat, next_ayat_n = 0, 1
            pasal_data[cur_pasal] = {"bab_number": cur_bab_number, "bab_title": cur_bab_title, "ayat": {0: []}}
            i += 1
            continue

        if cur_pasal is None:
            i += 1
            continue

        ayat_hit = next(
            (k for k in range(next_ayat_n, next_ayat_n + max_skip + 1)
             if ayat_re(k).match(text) or (is_explanation and ayat_label_re(k).match(text))),
            None,
        )
        ayat_dict = pasal_data[cur_pasal]["ayat"]
        if ayat_hit is not None:
            cur_ayat, next_ayat_n = ayat_hit, ayat_hit + 1
            ayat_dict[cur_ayat] = [lines[i]]
        else:
            ayat_dict[cur_ayat].append(lines[i])
        i += 1

    return pasal_data


def _joined(line_list: list[dict]) -> str:
    return tidy(" ".join(ln["text"] for ln in line_list))


def _span(line_list: list[dict]) -> tuple[list[int], float | None]:
    pages = sorted({ln["page_index"] for ln in line_list})
    scores = [ln["confidence"] for ln in line_list if ln.get("confidence") is not None]
    return pages, (round(sum(scores) / len(scores), 4) if scores else None)


def explanations_for_pasal(expl_pasal_data: dict[int, dict], pasal_n: int, n_body_ayat: int) -> dict[int, str]:
    """Per-ayat explanation text for one Pasal, matched 1:1 to body ayat
    numbers instead of gluing the whole Pasal's explanation onto every ayat.
    """
    data = expl_pasal_data.get(pasal_n)
    if data is None:
        return {}
    ayat_dict = data["ayat"]
    has_real_split = len(ayat_dict) > 1

    out: dict[int, str] = {}
    if has_real_split:
        for ayat_n, lns in ayat_dict.items():
            if ayat_n == 0:
                continue  # preamble text before the first ayat marker; not attributable to one ayat
            text = _joined(lns)
            out[ayat_n] = "" if TRIVIAL.match(text) else text
    else:
        text = _joined(ayat_dict.get(0, []))
        text = "" if TRIVIAL.match(text) else text
        if text:
            target_ayat = 1 if n_body_ayat > 1 else (next(iter(ayat_dict), 1) or 1)
            out[target_ayat if n_body_ayat > 1 else 1] = text
    return out



def build() -> list[dict]:
    records = []
    for kind, num, year, law, title in LAWS:
        pdf_path = find_pdf(kind, num, year)
        doc_dir = LAYOUT_DIR / pdf_path.stem
        lines = drop_preamble(flatten_lines(load_pages(doc_dir)))

        body_lines, pen_lines = split_sections(lines)
        pasal_data = parse_pasal_ayat(body_lines)
        expl_pasal_data = parse_pasal_ayat(pen_lines, bare_ok=True, is_explanation=True)

        for pasal_n, pdata in pasal_data.items():
            ayat_dict = pdata["ayat"]
            # Fold any pre-ayat-marker text (ayat 0) into ayat 1 instead of
            # emitting an ayat=null "pasal-level" row -- every chunk is ayat-level.
            if 0 in ayat_dict and len(ayat_dict) > 1:
                ayat_dict.setdefault(1, [])
                ayat_dict[1] = ayat_dict.pop(0) + ayat_dict[1]
            elif 0 in ayat_dict:
                ayat_dict[1] = ayat_dict.pop(0)

            body_ayat_numbers = sorted(ayat_dict)
            expl_by_ayat = explanations_for_pasal(expl_pasal_data, pasal_n, len(body_ayat_numbers))

            for order, ayat_n in enumerate(body_ayat_numbers):
                text = _joined(ayat_dict[ayat_n])
                if not text:
                    continue
                explanation = expl_by_ayat.get(ayat_n, "")
                page_numbers, ocr_confidence = _span(ayat_dict[ayat_n])
                citation = f"{law} Pasal {pasal_n} ayat ({ayat_n})"
                full = f"{law} tentang {title}, Pasal {pasal_n} ayat ({ayat_n}).\n{text}"
                if explanation:
                    full += f"\nPenjelasan Pasal {pasal_n} ayat ({ayat_n}): {explanation}"

                records.append({
                    "id": f"{law.replace(' ', '_').replace('/', '_')}_P{pasal_n}_A{ayat_n}",
                    "law_short": law,
                    "law_kind": kind,
                    "law_number": num,
                    "law_year": year,
                    "law_title": title,
                    "source_url": SOURCE_URL[law],
                    "bab_number": pdata["bab_number"],
                    "bab_title": pdata["bab_title"],
                    "pasal": pasal_n,
                    "ayat": ayat_n,
                    "order_in_pasal": order,
                    "citation": citation,
                    "has_explanation": bool(explanation),
                    "explanation": explanation,
                    "main": text,
                    "text": full,
                    "char_len": len(full),
                    "word_len": len(full.split()),
                    "page_numbers": page_numbers,
                    "ocr_confidence": ocr_confidence,
                    "extraction_source": "ocr_layout",
                })

    return records


if __name__ == "__main__":
    recs = build()
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs), encoding="utf-8")
    print("chunks:", len(recs), dict(Counter(r["law_short"] for r in recs)))
    print("with explanation:", sum(r["has_explanation"] for r in recs))
    null_ayat = sum(1 for r in recs if r["ayat"] is None)
    print("records with ayat=null (should be 0):", null_ayat)
    low_conf = [r for r in recs if r["ocr_confidence"] is not None and r["ocr_confidence"] < 0.9]
    print(f"chunks with mean OCR confidence < 0.9: {len(low_conf)}")
