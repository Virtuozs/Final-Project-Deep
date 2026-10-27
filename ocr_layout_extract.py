"""Layout-aware OCR extractor: groups OCR lines into real paragraphs using
PaddleOCR's LayoutDetection module, instead of the flat line-by-line dump
`ocr_extract.py` produces.

Why this exists: `ocr_extract.py` only sorts OCR lines into reading-order rows
(group_lines_into_rows) -- it has no idea which lines belong to the same
paragraph, title, or footer. reference/paddle-spike (q02_layout.py / q08_mapping.py,
see out/report.md "Q2: layout") found that PaddleOCR's `LayoutDetection` module
with model `PP-DocLayoutV2` returns, per page, a set of labeled blocks
(doc_title, paragraph_title, header, text, footer, table, seal, ...), each with
a `coordinate` box AND a populated per-box `order` field giving real reading
order -- the one layout model among those tested that actually exposes this.
Running it with `engine="onnxruntime"` is both faster and avoids an oneDNN
crash paddle-spike's README documents for this model/engine combination on CPU.

Pipeline per page:
    1. Rasterize the PDF page (fitz) and run it through PaddleOCR's
       DocPreprocessor (orientation + unwarping), same as ocr_extract.py.
    2. Run LayoutDetection (PP-DocLayoutV2) on the preprocessed image to get
       labeled blocks + reading order.
    3. Run PaddleOCR (text detection + recognition) on the same image to get
       text lines + boxes.
    4. Assign each OCR line to the layout block whose box contains the line's
       centroid (falling back to nearest block by center distance, or to an
       "unassigned" bucket if no blocks were found at all).
    5. Sort blocks by their layout `order`; order each block's lines top-to-bottom
       with row-overlap grouping (two text runs on the same visual line, e.g. a
       hanging list marker "2." and its clause text, get read left-to-right
       together instead of being interleaved by detection jitter in y0); join a
       block's lines with spaces into one paragraph (also fixing the missing-
       space-at-line-wrap defect seen when testing PPStructureV3's own markdown
       merger on this project's PDFs).
    6. Render to markdown: `doc_title` -> "# ", `paragraph_title`/`header` -> "## ",
       everything else -> a plain paragraph. Blocks are separated by a blank line.

Requires the same paddleocr/paddlepaddle environment as ocr_extract.py (this
project's own .venv, after `uv sync`, already has it).

Usage:
    python3 ocr_layout_extract.py raw_data/"UU Nomor 27 Tahun 2022.pdf" --out outputs_layout
    python3 ocr_layout_extract.py raw_data --out outputs_layout --max-pages 2 --no-images
    # only the combined outputs_layout/<stem>.md, no per-page page-N/ folders at all:
    python3 ocr_layout_extract.py raw_data --out outputs_layout --combined-only
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

import cv2
import fitz  # pymupdf

_THREADS = os.cpu_count()

# Layout labels from PP-DocLayoutV2 (see reference/paddle-spike/README.md, q02 section)
# that are headings rather than body paragraphs.
HEADING1_LABELS = {"doc_title"}
HEADING2_LABELS = {"paragraph_title", "header"}
# Visual blocks whose OCR text (if any) is not meaningful running text.
SKIP_LABELS = {"image", "figure", "chart", "table", "seal", "formula", "display_formula", "inline_formula"}


def _unwrap_result(result: Any) -> dict:
    """Normalize a Paddle/PaddleX result object into a plain dict, whether it
    already behaves like a dict or needs .json() first (ported from
    reference/paddle-spike/spike/common.py's result_dict + inner)."""
    if isinstance(result, dict):
        data = result
    else:
        data = getattr(result, "json", None)
        data = data() if callable(data) else result
    if isinstance(data, dict) and isinstance(data.get("res"), dict):
        return data["res"]
    return data if isinstance(data, dict) else {}


def _centroid(box: list[float]) -> tuple[float, float]:
    x0, y0, x1, y1 = box
    return (x0 + x1) / 2, (y0 + y1) / 2


def _contains(block_box: list[float], point: tuple[float, float]) -> bool:
    x0, y0, x1, y1 = block_box
    px, py = point
    return x0 <= px <= x1 and y0 <= py <= y1


def _center_distance(a: tuple[float, float], block_box: list[float]) -> float:
    bx, by = _centroid(block_box)
    return ((a[0] - bx) ** 2 + (a[1] - by) ** 2) ** 0.5


def order_lines_into_rows(lines: list[dict], overlap_ratio_thresh: float = 0.5) -> list[dict]:
    """Order lines top-to-bottom, left-to-right, but first group lines whose
    y-ranges overlap into the same "row". A flat (y0, x0) sort breaks on
    detection jitter: two text runs on the same visual line (e.g. a hanging
    list marker "2." and the wrapped clause text next to it) can land with
    slightly different y0, and a flat sort then interleaves them with the
    next/previous line instead of reading them left-to-right together.
    (Ported from ocr_extract.py's group_lines_into_rows.)
    """
    rows = []
    for ln in sorted(lines, key=lambda ln: ln["bbox"][1]):
        y1, y2 = ln["bbox"][1], ln["bbox"][3]
        for row in rows:
            ry1, ry2 = row["y1"], row["y2"]
            overlap = min(y2, ry2) - max(y1, ry1)
            min_height = min(y2 - y1, ry2 - ry1)
            if min_height > 0 and overlap / min_height > overlap_ratio_thresh:
                row["lines"].append(ln)
                row["y1"], row["y2"] = min(ry1, y1), max(ry2, y2)
                break
        else:
            rows.append({"y1": y1, "y2": y2, "lines": [ln]})

    rows.sort(key=lambda row: row["y1"])
    ordered = []
    for row in rows:
        row["lines"].sort(key=lambda ln: ln["bbox"][0])
        ordered.extend(row["lines"])
    return ordered


class LayoutAwareOcrExtractor:
    """Lazily loads DocPreprocessor, LayoutDetection and PaddleOCR once each."""

    def __init__(self, cpu_threads: int = _THREADS, layout_model: str = "PP-DocLayoutV2", engine: str = "onnxruntime"):
        self.cpu_threads = cpu_threads
        self.layout_model = layout_model
        self.engine = engine
        self._doc_preprocessor = None
        self._layout_detector = None
        self._ocr_pipeline = None

    @property
    def doc_preprocessor(self):
        if self._doc_preprocessor is None:
            from paddleocr import DocPreprocessor
            self._doc_preprocessor = DocPreprocessor(
                use_doc_orientation_classify=True,
                use_doc_unwarping=True,
                engine="onnxruntime",
                cpu_threads=self.cpu_threads,
            )
        return self._doc_preprocessor

    @property
    def layout_detector(self):
        if self._layout_detector is None:
            from paddleocr import LayoutDetection
            self._layout_detector = LayoutDetection(
                model_name=self.layout_model,
                engine=self.engine,
                cpu_threads=self.cpu_threads,
            )
        return self._layout_detector

    @property
    def ocr_pipeline(self):
        if self._ocr_pipeline is None:
            from paddleocr import PaddleOCR
            self._ocr_pipeline = PaddleOCR(
                text_detection_model_name="PP-OCRv6_medium_det",
                text_recognition_model_name="PP-OCRv6_medium_rec",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                return_word_box=False,
                enable_mkldnn=True,
                use_textline_orientation=False,
                engine="onnxruntime",
                cpu_threads=self.cpu_threads,
            )
        return self._ocr_pipeline

    def process_page_image(self, image_path: str) -> dict:
        """Preprocess, then run layout detection + OCR, then group lines into
        ordered paragraph blocks. Returns a page dict with "blocks",
        "unassigned_lines", "preprocessed_image" and "timing"."""
        t0 = time.perf_counter()
        preprocessed = list(self.doc_preprocessor.predict(input=image_path))[0]
        page_image = preprocessed["output_img"]
        t1 = time.perf_counter()

        layout_result = _unwrap_result(list(self.layout_detector.predict(input=page_image, batch_size=1))[0])
        t2 = time.perf_counter()

        ocr_result = _unwrap_result(list(self.ocr_pipeline.predict(input=page_image))[0])
        t3 = time.perf_counter()

        raw_blocks = [b for b in (layout_result.get("boxes") or []) if isinstance(b, dict) and b.get("coordinate")]
        blocks = [
            {
                "label": b.get("label", "?"),
                "score": b.get("score"),
                "bbox": [round(float(c), 2) for c in b["coordinate"]],
                "order": b.get("order"),
                "lines": [],
            }
            for b in raw_blocks
        ]

        texts = ocr_result.get("rec_texts") or []
        scores = ocr_result.get("rec_scores") or []
        boxes = ocr_result.get("rec_boxes")
        boxes = boxes.tolist() if hasattr(boxes, "tolist") else (boxes or [])

        unassigned = []
        for text, score, box in zip(texts, scores, boxes):
            line = {"text": text, "confidence": round(float(score), 4), "bbox": [round(float(c), 2) for c in box]}
            centroid = _centroid(box)
            containing = [blk for blk in blocks if _contains(blk["bbox"], centroid)]
            if containing:
                # smallest containing block, in case layout boxes are nested
                target = min(containing, key=lambda blk: (blk["bbox"][2] - blk["bbox"][0]) * (blk["bbox"][3] - blk["bbox"][1]))
                target["lines"].append(line)
            elif blocks:
                nearest = min(blocks, key=lambda blk: _center_distance(centroid, blk["bbox"]))
                nearest["lines"].append(line)
            else:
                unassigned.append(line)

        for blk in blocks:
            blk["lines"] = order_lines_into_rows(blk["lines"])
        unassigned = order_lines_into_rows(unassigned)

        # Reading order: layout `order` when present, else top-to-bottom by bbox y0.
        blocks.sort(key=lambda blk: (blk["order"] if blk["order"] is not None else blk["bbox"][1]))

        return {
            "blocks": blocks,
            "unassigned_lines": unassigned,
            "preprocessed_image": page_image,
            "timing": {
                "preprocess_seconds": round(t1 - t0, 3),
                "layout_seconds": round(t2 - t1, 3),
                "ocr_seconds": round(t3 - t2, 3),
                "total_seconds": round(t3 - t0, 3),
            },
        }

    def extract_pdf(
        self,
        pdf_path: Path,
        out_dir: Path,
        zoom: float = 2.0,
        save_images: bool = True,
        max_pages: int | None = None,
        combined_only: bool = False,
    ) -> list[str]:
        """combined_only=True skips writing any per-page .md/.json/.png files
        (the usual outputs_layout/<stem>/page-N/ tree isn't created at all) and
        only writes the final combined outputs_layout/<stem>.md at the end."""
        pdf_path = Path(pdf_path)
        doc_dir = out_dir / pdf_path.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        if not combined_only:
            doc_dir.mkdir(parents=True, exist_ok=True)

        mat = fitz.Matrix(zoom, zoom)
        page_texts = []

        with fitz.open(pdf_path) as doc, tempfile.TemporaryDirectory(prefix="ocr_layout_") as tmp_dir:
            tmp_dir = Path(tmp_dir)
            for i, page in enumerate(doc):
                if max_pages is not None and i >= max_pages:
                    break
                page_path = tmp_dir / f"page-{i}.png"
                page.get_pixmap(matrix=mat).save(str(page_path))

                page_data = self.process_page_image(str(page_path))
                markdown_text = page_to_markdown(page_data)

                if not combined_only:
                    page_dir = doc_dir / f"page-{i}"
                    page_dir.mkdir(parents=True, exist_ok=True)
                    if save_images:
                        shutil.copy(page_path, page_dir / f"page-{i}.png")
                        cv2.imwrite(str(page_dir / f"page-{i}-preprocessed.png"), page_data["preprocessed_image"])
                    (page_dir / f"page-{i}.md").write_text(markdown_text, encoding="utf-8")
                    (page_dir / f"page-{i}.json").write_text(
                        json.dumps(page_to_json(page_data), indent=2, ensure_ascii=False), encoding="utf-8"
                    )

                page_texts.append(markdown_text)
                n_lines = sum(len(b["lines"]) for b in page_data["blocks"]) + len(page_data["unassigned_lines"])
                print(
                    f"  page {i}: {len(page_data['blocks'])} blocks, {n_lines} lines, "
                    f"{page_data['timing']['total_seconds']}s "
                    f"(preprocess {page_data['timing']['preprocess_seconds']}s, "
                    f"layout {page_data['timing']['layout_seconds']}s, "
                    f"ocr {page_data['timing']['ocr_seconds']}s)"
                )

        full_text = "\f".join(page_texts)
        (out_dir / f"{pdf_path.stem}.md").write_text(full_text, encoding="utf-8")
        return page_texts


def page_to_markdown(page: dict) -> str:
    parts = []
    for blk in page["blocks"]:
        if blk["label"] in SKIP_LABELS or not blk["lines"]:
            continue
        text = " ".join(ln["text"] for ln in blk["lines"])
        if blk["label"] in HEADING1_LABELS:
            parts.append(f"# {text}")
        elif blk["label"] in HEADING2_LABELS:
            parts.append(f"## {text}")
        else:
            parts.append(text)
    if page["unassigned_lines"]:
        parts.append(" ".join(ln["text"] for ln in page["unassigned_lines"]))
    return "\n\n".join(parts)


def page_to_json(page: dict) -> dict:
    height, width = page["preprocessed_image"].shape[:2]
    return {
        "image_width": width,
        "image_height": height,
        "blocks": [
            {k: v for k, v in blk.items() if k != "lines"} | {"text": " ".join(ln["text"] for ln in blk["lines"]), "lines": blk["lines"]}
            for blk in page["blocks"]
        ],
        "unassigned_lines": page["unassigned_lines"],
    }


def iter_input_pdfs(input_path: Path) -> Iterable[Path]:
    if input_path.is_dir():
        yield from sorted(input_path.glob("*.pdf"))
    else:
        yield input_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="PDF file or directory of PDFs to OCR")
    parser.add_argument("--out", type=Path, default=Path("outputs_layout"), help="output directory")
    parser.add_argument("--zoom", type=float, default=2.0, help="rasterization zoom factor")
    parser.add_argument("--no-images", action="store_true", help="don't keep page PNGs, only text/json")
    parser.add_argument("--combined-only", action="store_true", help="skip writing per-page .md/.json/.png files; only write the final combined <stem>.md (implies --no-images)")
    parser.add_argument("--max-pages", type=int, default=None, help="only OCR the first N pages per PDF (useful for a quick test)")
    parser.add_argument("--layout-model", default="PP-DocLayoutV2", help="LayoutDetection model name (default: PP-DocLayoutV2, the only one with a populated per-box order field)")
    parser.add_argument("--engine", default="onnxruntime", help="inference engine for layout detection (default: onnxruntime; avoids a known oneDNN crash with PP-DocLayoutV2 on CPU)")
    args = parser.parse_args()

    pdfs = list(iter_input_pdfs(args.input))
    if not pdfs:
        raise SystemExit(f"no PDFs found at {args.input}")

    args.out.mkdir(parents=True, exist_ok=True)
    extractor = LayoutAwareOcrExtractor(layout_model=args.layout_model, engine=args.engine)

    for pdf_path in pdfs:
        print(f"[{pdf_path.name}]")
        t0 = time.perf_counter()
        extractor.extract_pdf(
            pdf_path, args.out, zoom=args.zoom, save_images=not args.no_images and not args.combined_only,
            max_pages=args.max_pages, combined_only=args.combined_only,
        )
        print(f"  done in {time.perf_counter() - t0:.1f}s -> {args.out / (pdf_path.stem + '.md')}")


if __name__ == "__main__":
    main()
