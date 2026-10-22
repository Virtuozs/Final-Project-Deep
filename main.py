import re, json, pathlib
import fitz  # PyMuPDF
from collections import Counter

RAW = pathlib.Path("raw_data")
OUT = pathlib.Path("corpus.jsonl")

LAWS = [  # (kind, number, year, short name, title)
    ("UU", 14, 2008, "UU 14/2008", "Keterbukaan Informasi Publik"),
    ("PP", 61, 2010, "PP 61/2010", "Pelaksanaan UU 14/2008 tentang KIP"),
    ("UU", 25, 2009, "UU 25/2009", "Pelayanan Publik"),
    ("UU", 27, 2022, "UU 27/2022", "Pelindungan Data Pribadi"),
]

def find_pdf(kind, num, year):
    pat = re.compile(rf"^{kind}\D*0*{num}\D+{year}", re.I)
    for p in RAW.glob("*.pdf"):
        if pat.match(p.stem):
            return p
    raise FileNotFoundError(f"No PDF for {kind} {num}/{year} in {RAW.resolve()}")

# OCR confusions (UU 27/2022 has an OCR text layer)
OCR = {"0": "0Oo", "1": "1IlLt|", "2": "2Zz", "5": "5S", "7": "7T1Il", "8": "88B"}
def digit_class(d): return "[" + OCR.get(d, d) + "]"
def heading_re(n, bare_ok=False):
    pre = r"(?:Pas[a-zA-Z0-9]{0,2}\s*)" + ("?" if bare_ok else "")
    return re.compile(r"^\s*" + pre + "".join(digit_class(d) for d in str(n)) + r"\s*$")

def read_pages(pdf):
    with fitz.open(pdf) as doc:
        return [page.get_text() for page in doc]

CATCHWORD = re.compile(r"^.{1,45}?(?:\s*\.\s*\.\s*\.|\s*…)\s*$")          # "Pasal 14 …"
PAGENO    = re.compile(r"^\s*-\s*[0-9tIlO]{1,3}\s*-?\s*(?=Pas|BAB|$)")    # "- 10 Pasal 14"
NOISE     = re.compile(r"^(SK No .*|SALINAN|[PF]RES\S{3,6}|\S{0,12}[LI]IK\s+IN\S{3,}"
                       r"|[PF]RES\S{3,6}\s+\S{0,12}[LI]IK\s+IN\S{3,})\s*$")  # page headers (incl. OCR variants)

def join_split_headings(lines):
    """'Pasal' and its number sometimes land on separate lines -> re-join."""
    out, i = [], 0
    while i < len(lines):
        ln = lines[i].strip()
        if re.fullmatch(r"Pas[a-zA-Z0-9]{0,2}", ln) and i + 1 < len(lines) \
           and re.fullmatch(r"[0-9A-Za-z|]{1,3}", lines[i + 1].strip()):
            out.append(ln + " " + lines[i + 1].strip()); i += 2
        else:
            out.append(lines[i]); i += 1
    return out

def clean_page(page):
    out = []
    for ln in join_split_headings(page.splitlines()):
        ln = PAGENO.sub("", ln).strip()
        if not ln or NOISE.match(ln) or CATCHWORD.match(ln) or re.fullmatch(r"Pas[a-zA-Z0-9]{0,2}", ln):
            continue
        out.append(ln)
    return out

def split_sections(lines):
    """body = before the PENJELASAN line; elucidation = after 'PASAL DEMI PASAL'"""
    idx = next((i for i, l in enumerate(lines)
                if re.fullmatch(r"PENJ\w{1,3}[A-Z,]{0,2}ASAN", l.strip().upper())), None)
    if idx is None:
        return lines, []
    body, pen = lines[:idx], lines[idx:]
    j = next((i for i, l in enumerate(pen) if re.search(r"PASAL\s*DEMI\s*PASAL", l, re.I)), 0)
    return body, pen[j + 1:]

def split_by_pasal(lines, max_skip=2, name="", bare_ok=False):
    """Accept a heading only if it is Pasal n, n+1 or n+2 (n = next expected)."""
    chunks, cur, n = {}, None, 1
    for ln in lines:
        hit = next((k for k in range(n, n + max_skip + 1) if heading_re(k, bare_ok).match(ln)), None)
        if hit is not None:
            if hit != n:
                print(f"  [warn] {name}: expected Pasal {n}, found {hit}")
            cur = hit; chunks[cur] = []; n = hit + 1
        elif cur is not None:
            chunks[cur].append(ln)
    return {k: " ".join(v) for k, v in chunks.items()}

TAIL = re.compile(r"(Agar\s+setiap\s+orang\s+mengetahuinya|TAMBAHAN\s+LEMBARAN\s+NEGARA).*", re.S)
TRIVIAL = re.compile(r"^\s*cukup\s+jelas\.?\s*$", re.I)

def tidy(t):
    t = TAIL.sub("", t)   # drop signature block / Lembaran Negara footer after the last Pasal
    t = re.sub(r"\s+", " ", t).strip().replace("UndangUndang", "Undang-Undang")
    return re.sub(r"(?<=\w)- (?=[a-z])", "-", t)

def build():
    records = []
    for kind, num, year, law, title in LAWS:
        pages = read_pages(find_pdf(kind, num, year))
        lines = [l for p in pages for l in clean_page(p)]
        body, pen = split_sections(lines)
        main = split_by_pasal(body, name=law)
        expl = split_by_pasal(pen, name=law + " penjelasan", bare_ok=True)
        for n, text in main.items():
            e = tidy(expl.get(n, ""))
            has_e = bool(e) and not TRIVIAL.match(e)
            full = f"{law} tentang {title}, Pasal {n}.\n{tidy(text)}"
            if has_e:
                full += f"\nPenjelasan Pasal {n}: {e}"
            records.append({"id": f"{law.replace(' ', '_').replace('/', '_')}_P{n}",
                            "law": law, "pasal": n, "has_explanation": has_e,
                            "main": tidy(text), "explanation": e, "text": full})
    return records

if __name__ == "__main__":
    recs = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs), encoding="utf-8")
    print("chunks:", len(recs), dict(Counter(r["law"] for r in recs)))
    print("with explanation:", sum(r["has_explanation"] for r in recs))