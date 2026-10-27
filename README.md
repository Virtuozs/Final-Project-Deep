# Final Project Deep Indonesian Law Corpus

This is initialize project that builds an ayat-level (article/sub-point) corpus from four Indonesian law PDFs
in `raw_data/`, via OCR instead of each PDF's own (sometimes unreliable) text
layer.

## Pipeline

```
raw_data/*.pdf
    -> ocr_layout_extract.py   (PaddleOCR + layout detection, per-page JSON)
    -> corpus_build_ocr.py     (Pasal/ayat parsing -> corpus-ocr.jsonl)
```

- `ocr_layout_extract.py` rasterizes each PDF page and runs it through
  PaddleOCR's `DocPreprocessor` (orientation/unwarp), `LayoutDetection`
  (`PP-DocLayoutV2` — labeled blocks with reading order) and `PaddleOCR`
  (text + per-line confidence). Output: `outputs_layout/<pdf-stem>/page-N/page-N.json`.
- `law_text_utils.py` is a shared helper module (law lookup, OCR-confusion-
  tolerant Pasal/ayat heading regex, text cleanup). Also runnable standalone
  to build a Pasal-level corpus straight from PyMuPDF's native text layer.
- `corpus_build_ocr.py` consumes `outputs_layout/`'s per-page JSON and parses
  it into `corpus-ocr.jsonl`: one record per ayat, with BAB/Pasal/ayat
  citation, the matching Penjelasan (explanation) text, page numbers, and
  mean OCR confidence.

## Setup

This project uses [uv](https://docs.astral.sh/uv/). Install it once:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then from this directory:

```bash
uv sync
```

This creates `.venv/` and installs everything pinned in `uv.lock`
(`pymupdf`, `paddleocr`, `paddlepaddle`, `paddlex[ocr]`, `onnxruntime`,
`jupyter`/`ipykernel`). No separate activation step is needed with provided prefix
commands `uv run` it uses that environment automatically.

The first run of any OCR/layout model downloads its weights (cached under
`~/.paddlex/official_models/`), so expect the very first `ocr_layout_extract.py`
run to be slower than later ones.

## Running it

### 1. OCR + layout extraction

```bash
# one PDF
uv run python ocr_layout_extract.py "raw_data/PP 61 Tahun 2010.pdf" --out outputs_layout

# every PDF in raw_data/
uv run python ocr_layout_extract.py raw_data --out outputs_layout
```

`corpus_build_ocr.py` needs the per-page JSON, so don't pass `--combined-only`
for that run. Useful flags:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--out PATH` | `outputs_layout` | output directory |
| `--max-pages N` | all | only OCR the first N pages per PDF (quick test) |
| `--no-images` | off | keep text/json, drop the page PNGs |
| `--combined-only` | off | skip all per-page files, write only a combined `<stem>.md` |
| `--zoom N` | `2.0` | rasterization zoom factor |

OCR runs at roughly 10–20s per page on CPU, so a full run over all four PDFs
(~200 pages) takes about an hour. `--max-pages` is the fast way to sanity
check a change before committing to a full run.

### 2. Build the corpus

```bash
uv run python corpus_build_ocr.py
```

Reads `outputs_layout/`, writes `corpus-ocr.jsonl` to this directory, and
prints a summary (chunk count per law, how many have an explanation, mean
OCR confidence below 0.9).

### Optional: native-text corpus

`law_text_utils.py` can also build a corpus directly from each PDF's own
text layer (no OCR, much faster, but subject to that PDF's own OCR/text
quality):

```bash
uv run python law_text_utils.py
```

Writes `corpus.jsonl` (Pasal-level, not ayat-level).

## Output schema (`corpus-ocr.jsonl`)

One JSON object per line, one record per ayat:

```json
{
  "id": "UU_14_2008_P2_A1",
  "law_short": "UU 14/2008",
  "law_kind": "UU", "law_number": 14, "law_year": 2008,
  "law_title": "Keterbukaan Informasi Publik",
  "source_url": "...",
  "bab_number": "BAB II", "bab_title": "ASAS DAN TUJUAN",
  "pasal": 2, "ayat": 1, "order_in_pasal": 0,
  "citation": "UU 14/2008 Pasal 2 ayat (1)",
  "has_explanation": true,
  "explanation": "...",
  "main": "(1) Setiap Informasi Publik bersifat terbuka...",
  "text": "UU 14/2008 tentang ..., Pasal 2 ayat (1).\n...",
  "char_len": 1072, "word_len": 141,
  "page_numbers": [3],
  "ocr_confidence": 0.987,
  "extraction_source": "ocr_layout"
}
```
