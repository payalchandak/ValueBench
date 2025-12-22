from __future__ import annotations

import os
import json
from datetime import datetime
from dataclasses import dataclass
import logging
from typing import Any, Dict, Iterable, List, Optional, Union, Tuple, Literal

from json import JSONDecodeError
from itertools import groupby
from pathlib import Path

import pdfplumber
from pdfminer.pdfparser import PDFSyntaxError
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pydantic import BaseModel

from all_the_llms import LLM
from prompt_manager import PromptManager
from response_models.extract import TocDetectionResult, SectionCases, LiteratureCurationResult


logger = logging.getLogger(__name__)

@dataclass
class OutlineEntry:
    """Logical entry (e.g., section) in the document with a starting page."""
    title: str
    start_page: int  
    level: int = 0   


@dataclass
class Section:
    """Contiguous range of pages belonging to one logical chunk."""
    title: str
    start_page: int  
    end_page: int   


@dataclass
class SectionExtractionResult:
    """Result of LLM extraction for a given section."""
    section: Section
    payload: Dict[str, Any]


class PdfCaseExtractor:
    """
      1. Discover an outline for a PDF (native outline or LLM-detected TOC).
      2. Turn the outline into page-based sections (or fixed-size chunks).
      3. Send each section to an LLM to extract cases as JSON.
    """

    def __init__(
        self,
        pdf_path: str,
        model_key: str = "gpt-5-mini",
        chunk_size: int = 25,
        toc_temperature: float = 1.0,
        case_temperature: float = 1.0,
    ):
        self.pdf_path = pdf_path
        self.chunk_size = chunk_size
        self.toc_temperature = toc_temperature
        self.case_temperature = case_temperature

        logger.info(
            "Initializing PdfCaseExtractor: pdf_path=%s, model_key=%s, chunk_size=%d",
            pdf_path,
            model_key,
            chunk_size,
        )

        self.llm = LLM(model_key, routing_judge=model_key)
        self.pm = PromptManager()

        self.reader = PdfReader(self.pdf_path)
        self.num_pages = len(self.reader.pages)
        logger.info("Loaded PDF with %d pages", self.num_pages)

    def _walk_pypdf_outline(self) -> List[OutlineEntry]:
        """
        Flatten pypdf nested outline into a list of OutlineEntry objects.
        """
        raw_outline = getattr(self.reader, "outline", None) or getattr(
            self.reader, "outlines", []
        )
        entries: List[OutlineEntry] = []

        def _walk(items: Iterable[Union[list, Any]], level: int = 0):
            for item in items:
                if isinstance(item, list):
                    _walk(item, level + 1)
                else:
                    try:
                        page_index = self.reader.get_destination_page_number(item)
                    except (PdfReadError, KeyError, IndexError, ValueError) as e:
                        logger.debug(
                            "Skipping outline destination %r due to PDF error: %s",
                            getattr(item, "title", repr(item)),
                            e,
                        )
                        continue

                    title = str(item.title).strip()
                    entries.append(
                        OutlineEntry(title=title, start_page=page_index, level=level)
                    )

        _walk(raw_outline, level=0)
        entries.sort(key=lambda e: e.start_page)
        logger.debug("Found %d raw outline entries", len(entries))
        return entries

    @staticmethod
    def _filter_outline_entries(entries: List[OutlineEntry]) -> List[OutlineEntry]:
        """
        Optional filter for outline entries.
        Currently keeps all non-empty titles.
        """
        cleaned: List[OutlineEntry] = []
        for e in entries:
            title = e.title.strip()
            if not title:
                continue
            cleaned.append(e)
        return cleaned

    def _get_first_pages_text(self, max_pages: int = 20) -> str:
        """
        Extract plain text from the first N pages for TOC detection.

        Prefer pdfplumber for better layout, but fall back to pypdf if needed.
        """
        logger.debug("Extracting first %d pages for TOC detection", max_pages)

        texts: List[str] = []
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                num = min(max_pages, len(pdf.pages))
                for i in range(num):
                    page = pdf.pages[i]
                    txt = page.extract_text(
                        x_tolerance=1.0,
                        y_tolerance=1.0,
                    ) or ""
                    texts.append(f"\n\n=== PAGE {i+1} ===\n{txt}")
            return "\n".join(texts)

        except (FileNotFoundError, PermissionError, OSError, IndexError, PDFSyntaxError) as e:
            logger.warning(
                "pdfplumber failed while extracting first pages for TOC; "
                "falling back to pypdf: %s",
                e,
            )

        texts = []
        for i, page in enumerate(self.reader.pages):
            if i >= max_pages:
                break
            txt = page.extract_text() or ""
            texts.append(f"\n\n=== PAGE {i+1} ===\n{txt}")
        return "\n".join(texts)

    def _ask_llm_for_toc(self) -> Dict[str, Any]:
        """
        Ask the LLM (via structured completion + Jinja prompts)
        to detect and extract a TOC, returning a plain JSON-like dict.
        """
        logger.info("Calling LLM for TOC detection")

        pages_text = self._get_first_pages_text(max_pages=20)

        messages = self.pm.build_messages(
            "workflows/pdf_toc",
            {
                "pages_text": pages_text,
            },
        )

        result: TocDetectionResult = self.llm.structured_completion(
            messages=messages,
            response_model=TocDetectionResult,
        )

        toc_json: Dict[str, Any] = {
            "has_toc": result.has_toc,
            "entries": [
                {"title": e.title, "page_label": e.page_label}
                for e in result.entries
            ],
        }

        logger.info("TOC detection complete; has_toc=%s", toc_json.get("has_toc"))
        return toc_json

    def _map_toc_to_outline_entries(self, toc_json: Dict[str, Any]) -> List[OutlineEntry]:
        """
        Convert LLM-derived TOC JSON into OutlineEntry list.
        Uses page_labels when available; falls back to integer page numbers.
        """
        if not toc_json.get("has_toc"):
            logger.info("TOC JSON indicates no table of contents found")
            return []

        entries: List[OutlineEntry] = []

        label_to_index: Dict[str, int] = {}

        labels = getattr(self.reader, "page_labels", None)
        if labels is None and hasattr(self.reader, "get_page_labels"):
            try:
                labels = self.reader.get_page_labels()
            except (PdfReadError, KeyError, TypeError) as e:
                logger.warning(
                    "Failed to get page labels via get_page_labels: %s",
                    e,
                )
                labels = None
            except Exception:
                logger.exception("Unexpected error from get_page_labels()")
                raise

        if labels:
            if isinstance(labels, dict):
                for idx, label in labels.items():
                    if label is None:
                        continue
                    label_to_index[str(label)] = int(idx)
            elif isinstance(labels, list):
                for idx, label in enumerate(labels):
                    if label is None:
                        continue
                    label_to_index[str(label)] = idx

        logger.debug("Built label_to_index mapping for %d labels", len(label_to_index))

        for item in toc_json.get("entries", []):
            title = str(item.get("title", "")).strip()
            if not title:
                continue

            label = str(item.get("page_label", "")).strip()
            if not label:
                continue

            page_index: Optional[int] = None

            if label_to_index:
                page_index = label_to_index.get(label)

            if page_index is None:
                try:
                    page_num = int(label)
                    page_index = max(0, page_num - 1)
                except ValueError:
                    logger.debug("Skipping TOC entry with unmappable label %r", label)
                    continue

            entries.append(OutlineEntry(title=title, start_page=page_index, level=0))

        entries.sort(key=lambda e: e.start_page)
        logger.info("Mapped %d TOC entries into outline entries", len(entries))
        return entries

    def find_outline_or_toc(self) -> List[OutlineEntry]:
        """
        Step 1: Find an outline for the PDF.
        - Try native PDF outline (bookmarks).
        """

        logger.info("Attempting to discover outline or TOC...")

        outline_entries = self._walk_pypdf_outline()
        filtered_outline = self._filter_outline_entries(outline_entries)
        if filtered_outline:
            logger.info(
                "Using native PDF outline with %d entries", len(filtered_outline)
            )
            return filtered_outline
        

        toc_json = self._ask_llm_for_toc()
        toc_outline = self._map_toc_to_outline_entries(toc_json)
        if toc_outline:
            logger.info(
                "Using LLM-derived TOC outline with %d entries", len(toc_outline)
            )
            return toc_outline
        logger.info("No outline or TOC found; will use fixed-size chunks")
        return []

    def build_sections(self, outline: Optional[List[OutlineEntry]] = None) -> List[Section]:
        """
        Turn OutlineEntry(start_page) list into contiguous page ranges (Sections).

        Behavior:
        - If outline is empty/None: use fixed-size chunks over the full document.
        - Drop outline entries with out-of-range start_page.
        - For entries that share the same start_page:
            * prefer deeper levels (higher `level`),
            * but CONCATENATE their titles into a single combined heading.
        """

        if not outline:
            sections: List[Section] = []
            for start in range(0, self.num_pages, self.chunk_size):
                end = min(start + self.chunk_size - 1, self.num_pages - 1)
                sections.append(
                    Section(
                        title=f"CHUNK_{start+1}_to_{end+1}",
                        start_page=start,
                        end_page=end,
                    )
                )
            logger.info(
                "No outline provided; built %d fixed-size sections (chunk_size=%d)",
                len(sections),
                self.chunk_size,
            )
            return sections

        valid_outline: List[OutlineEntry] = []
        for e in outline:
            if 0 <= e.start_page < self.num_pages:
                valid_outline.append(e)
            else:
                logger.warning(
                    "Dropping outline entry '%s' with out-of-range start_page=%d (num_pages=%d)",
                    e.title,
                    e.start_page,
                    self.num_pages,
                )

        if not valid_outline:
            logger.warning(
                "All outline entries invalid; falling back to fixed-size chunks."
            )
            return self.build_sections(outline=None)

        outline_sorted = sorted(valid_outline, key=lambda e: (e.start_page, e.level))

        merged_entries: List[OutlineEntry] = []

        for start_page, group_iter in groupby(outline_sorted, key=lambda e: e.start_page):
            group = list(group_iter)

            group.sort(key=lambda e: e.level)

            titles = [g.title.strip() for g in group if g.title and g.title.strip()]
            if not titles:
                continue

            if len(titles) == 1:
                combined_title = titles[0]
            else:
                combined_title = " - ".join(titles)

            max_level = max(e.level for e in group)

            merged_entries.append(
                OutlineEntry(
                    title=combined_title,
                    start_page=start_page,
                    level=max_level,
                )
            )

        merged_entries.sort(key=lambda e: e.start_page)

        sections: List[Section] = []
        for i, entry in enumerate(merged_entries):
            start = entry.start_page
            if i + 1 < len(merged_entries):
                end = merged_entries[i + 1].start_page - 1
            else:
                end = self.num_pages - 1

            if end < start:
                logger.warning(
                    "Skipping malformed section for '%s': end_page (%d) < start_page (%d)",
                    entry.title,
                    end,
                    start,
                )
                continue

            sections.append(
                Section(
                    title=entry.title,
                    start_page=start,
                    end_page=end,
                )
            )

        logger.info(
            "Built %d sections from %d merged outline entries (original valid entries=%d)",
            len(sections),
            len(merged_entries),
            len(valid_outline),
        )
        return sections

    def extract_section_text(self, section: Section) -> str:
        """
        Extract text for a given Section from the PDF.
        """
        logger.debug(
            "Extracting text for section '%s' (pages %d-%d)",
            section.title,
            section.start_page + 1,
            section.end_page + 1,
        )
        texts: List[str] = []

        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                for page_idx in range(section.start_page, section.end_page + 1):
                    if not (0 <= page_idx < self.num_pages):
                        logger.warning(
                            "Section '%s' refers to out-of-range page_idx=%d (num_pages=%d); "
                            "stopping early for this section.",
                            section.title,
                            page_idx,
                            self.num_pages,
                        )
                        break

                    page = pdf.pages[page_idx]
                    txt = page.extract_text(
                        x_tolerance=1.0,
                        y_tolerance=1.0,
                    ) or ""
                    texts.append(f"\n\n=== PAGE {page_idx+1} ===\n{txt}")
            return "\n".join(texts)

        except (FileNotFoundError, PermissionError, OSError, IndexError, PDFSyntaxError) as e:
            logger.warning(
                "pdfplumber failed for section '%s'; falling back to pypdf: %s",
                section.title,
                e,
            )


        for page_idx in range(section.start_page, section.end_page + 1):
            if not (0 <= page_idx < self.num_pages):
                logger.warning(
                    "Section '%s' refers to out-of-range page_idx=%d "
                    "(num_pages=%d); stopping early for this section.",
                    section.title,
                    page_idx,
                    self.num_pages,
                )
                break
            page = self.reader.pages[page_idx]
            txt = page.extract_text() or ""
            texts.append(f"\n\n=== PAGE {page_idx+1} ===\n{txt}")
        return "\n".join(texts)

    def extract_cases_for_section(self, section: Section, section_text: str) -> List[str]:
        """
        Send a section's text to the LLM and get back a list of case texts.
        """
        logger.info(
            "Calling LLM to extract cases for section '%s' (chars=%d)",
            section.title,
            len(section_text),
        )

        messages = self.pm.build_messages(
            "workflows/pdf_cases",
            {
                "section_title": section.title,
                "section_text": section_text,
            },
        )
        result: SectionCases = self.llm.structured_completion(
            messages=messages,
            response_model=SectionCases,
        )

        print("Result: ", result)
        cases = [str(case) for case in result.cases]
        logger.debug(
            "LLM returned %d cases for section '%s'",
            len(cases),
            section.title,
        )

        return cases
  
    def run(self) -> List[SectionExtractionResult]:
        """
        Full pipeline:
          1) FIND OUTLINE / TOC (optional)
          2) SPLIT into sections
          3) EXTRACT cases from each section via LLM
        """
        logger.info("Starting PDF case extraction pipeline")
        outline = self.find_outline_or_toc()
        sections = self.build_sections(outline)
        logger.info("Processing %d sections", len(sections))
        results: List[SectionExtractionResult] = []

        for idx, section in enumerate(sections, start=1):
            logger.info("Processing section %d/%d: '%s'", idx, len(sections), section.title)
            section_text = self.extract_section_text(section)
            if len(section_text.strip()) < 100:
                logger.debug(
                    "Skipping tiny section '%s' (len=%d)",
                    section.title,
                    len(section_text.strip()),
                )
                continue

            try:
                cases = self.extract_cases_for_section(section, section_text)
            except (JSONDecodeError, ValueError) as e:
                logger.warning(
                    "Skipping section '%s' due to JSON/parse error: %s",
                    section.title,
                    e,
                )
                continue
            except Exception:
                logger.exception(
                    "Unexpected error while extracting cases for section '%s'",
                    section.title,
                )
                raise

            logger.info("Extracted %d cases from section '%s'", len(cases), section.title)
            if cases:
                results.append(SectionExtractionResult(section=section, payload=cases))
        
        logger.info("Finished extraction. Sections with cases: %d", len(results))
        return results

    @staticmethod
    def save_results_as_json(
        results: List[SectionExtractionResult],
        output_path: str,
    ) -> None:
        aggregated: Dict[str, Any] = {}
        for idx, res in enumerate(results, start=1):
            section_key = f"section_{idx}"
            aggregated[section_key] = {
                "section_title": res.section.title,
                "start_page": res.section.start_page,
                "end_page": res.section.end_page,
                "cases": res.payload,  
            }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(aggregated, f, ensure_ascii=False, indent=2)
        logger.info("Saved aggregated results to %s", output_path)


class CurateLiteratureCase:
    """
    Stage after extraction:
    - Decide whether the extracted text looks like a real *clinical* case involving a decision (usable).
    - Classify scenario_type as:
        * "within": decision for a single patient
        * "between": decision allocating/comparing between patients/groups/resources
    - Identify two values in conflict (from the correct value set).

    IMPORTANT:
    - Do NOT rewrite the case.
    - Output the case text as-is in the "case" field.
    """

    def __init__(
        self,
        model_key: str = "gpt-5-mini",
        temperature: float = 1.0,
        max_chars: int = 12000,
    ):
        self.model_key = model_key
        self.temperature = temperature
        self.max_chars = max_chars

        self.llm = LLM(model_key, routing_judge=model_key)
        self.pm = PromptManager()

    @staticmethod
    def _iter_cases_from_extracted(extracted: Any) -> Iterable[Dict[str, Any]]:
        """
        Supports the aggregated JSON produced by PdfCaseExtractor.save_results_as_json:

        {
          "section_1": {
            "section_title": "...",
            "start_page": 0,
            "end_page": 9,
            "cases": ["case 1 text", "case 2 text", ...]  # List format (new)
            # OR
            "cases": {"case 1": "...", "case 2": "..."}  # Dict format (old, for backward compatibility)
          },
          ...
        }

        Also supports an optional flat list format.
        """
        if isinstance(extracted, dict):
            for section_key, sec in (extracted or {}).items():
                sec = sec or {}
                cases_data = sec.get("cases")
                if cases_data is None:
                    continue
                if isinstance(cases_data, dict):
                    for case_key, text in cases_data.items():
                        yield {
                            "source_case_id": f"{section_key}/{case_key}",
                            "section_title": sec.get("section_title"),
                            "start_page": sec.get("start_page"),
                            "end_page": sec.get("end_page"),
                            "raw_text": text,
                        }
                elif isinstance(cases_data, list):
                    for idx, text in enumerate(cases_data):
                        yield {
                            "source_case_id": f"{section_key}/case_{idx+1}",
                            "section_title": sec.get("section_title"),
                            "start_page": sec.get("start_page"),
                            "end_page": sec.get("end_page"),
                            "raw_text": str(text),
                        }
            return

        if isinstance(extracted, list):
            for idx, c in enumerate(extracted):
                if not isinstance(c, dict):
                    continue
                raw_text = c.get("text") or c.get("case") or ""
                yield {
                    "source_case_id": c.get("id") or f"case_{idx+1}",
                    "section_title": c.get("section_title"),
                    "start_page": c.get("start_page"),
                    "end_page": c.get("end_page"),
                    "raw_text": raw_text,
                }
            return

        raise ValueError(f"Unsupported extracted format: {type(extracted)}")

    def curate_one(self, case_text: str) -> Dict[str, Any]:
        """
        Returns exactly:
        {
          "usable": true|false,
          "reason": "...",
          "scenario_type": "within"|"between"|None,
          "value_1": str|None,
          "value_2": str|None,
          "case": str|None
        }
        """
        if not (case_text or "").strip():
            return {
                "usable": False,
                "reason": "Empty text",
                "scenario_type": None,
                "value_1": None,
                "value_2": None,
                "case": None,
            }

        text = case_text.strip()
        if len(text) > self.max_chars:
            text = text[: self.max_chars] + "\n...[TRUNCATED]"

        messages = self.pm.build_messages(
            "workflows/lit_classify",
            {"case_text": text},
        )

        try:
            parsed: LiteratureCurationResult = self.llm.structured_completion(
                messages=messages,
                response_model=LiteratureCurationResult,
            )
        except Exception as e:
            logger.exception(
                "Unexpected error while classifying cases: '%s'",
                e,
            )
            return {
                "usable": False,
                "reason": f"LLM/parse failure: {type(e).__name__}",
                "scenario_type": None,
                "value_1": None,
                "value_2": None,
                "case": None,
            }

        return parsed.model_dump()

    def curate_all(self, extracted: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Returns:
          - all_curated: flat list of all curated outputs (usable + unusable)
          - usable_curated: flat list of usable outputs only

        Each item is augmented with provenance:
          source_case_id, section_title, start_page, end_page
        """
        all_curated: List[Dict[str, Any]] = []
        usable_curated: List[Dict[str, Any]] = []

        for item in self._iter_cases_from_extracted(extracted):
            raw_text = item.get("raw_text") or ""
            curated = self.curate_one(raw_text)

            curated_with_meta = {
                **curated,
                "source_case_id": item.get("source_case_id"),
                "section_title": item.get("section_title"),
                "start_page": item.get("start_page"),
                "end_page": item.get("end_page"),
            }

            all_curated.append(curated_with_meta)
            if curated_with_meta.get("usable") is True:
                usable_curated.append(curated_with_meta)

        logger.info(
            "Curated literature cases: total=%d usable=%d",
            len(all_curated),
            len(usable_curated),
        )
        return all_curated, usable_curated


InputKind = Literal["pdf", "pdf_dir", "json", "json_dir"]


@dataclass(frozen=True)
class PipelineConfig:
    model_key: str = "gpt-5-mini"

    # extraction
    chunk_size: int = 25
    toc_temperature: float = 1.0
    case_temperature: float = 1.0

    # curation
    do_curate: bool = True
    curate_temperature: float = 1.0

    # outputs
    raw_out_dir: str = r"extracted_cases\raw_cases"
    curated_out_dir: str = r"extracted_cases\curated_cases"

    # file selection
    input_kind: InputKind = "pdf_dir"
    input_path: str = r"data/docs/"  # file or folder depending on input_kind 

    # naming
    run_timestamp: Optional[str] = None  # if None -> generated once per run
    overwrite: bool = False              # if False -> skip writing when file exists


def _ensure_dir(p: str) -> None:
    Path(p).mkdir(parents=True, exist_ok=True)


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d-%H-%M")


def _iter_pdfs(path: str) -> List[Path]:
    p = Path(path)
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted([x for x in p.rglob("*.pdf") if x.is_file()])
    raise FileNotFoundError(f"PDF path not found: {path}")


def _iter_jsons(path: str) -> List[Path]:
    p = Path(path)
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted([x for x in p.rglob("*.json") if x.is_file()])
    raise FileNotFoundError(f"JSON path not found: {path}")


def _safe_write_json(path: Path, payload: Any, *, overwrite: bool) -> bool:
    if path.exists() and not overwrite:
        logger.info("Output exists; skipping (overwrite=False): %s", str(path))
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return True


def _aggregate_extraction_results(extracted_results: List["SectionExtractionResult"]) -> Dict[str, Any]:
    """
    Same shape as your old save_results_as_json() output, but returned as dict.
    """
    extracted: Dict[str, Any] = {}
    for idx, res in enumerate(extracted_results, start=1):
        section_key = f"section_{idx}"
        extracted[section_key] = {
            "section_title": res.section.title,
            "start_page": res.section.start_page,
            "end_page": res.section.end_page,
            "cases": res.payload, 
        }
    return extracted


def run_on_pdf(pdf_path: str, *, cfg: PipelineConfig) -> Dict[str, Any]:
    """
    Extract from ONE PDF (always), then optionally curate.
    Saves:
      - extracted_cases/raw_cases/<stem>_<ts>_raw.json
      - extracted_cases/curated_cases/<stem>_<ts>_{all,usable}.json  (if cfg.do_curate)
    Returns:
      {"source": ..., "raw_path": ..., "curated_all_path": ..., "curated_usable_path": ..., "extracted": ..., "curated_all": ..., "curated_usable": ...}
    """
    ts = cfg.run_timestamp or _ts()
    stem = Path(pdf_path).stem

    _ensure_dir(cfg.raw_out_dir)
    _ensure_dir(cfg.curated_out_dir)

    raw_out = Path(cfg.raw_out_dir) / f"{stem}_{ts}_raw.json"
    curated_all_out = Path(cfg.curated_out_dir) / f"{stem}_{ts}_all.json"
    curated_usable_out = Path(cfg.curated_out_dir) / f"{stem}_{ts}_usable.json"

    extractor = PdfCaseExtractor(
        pdf_path=pdf_path,
        model_key=cfg.model_key,
        chunk_size=cfg.chunk_size,
        toc_temperature=cfg.toc_temperature,
        case_temperature=cfg.case_temperature,
    )
    extracted_results = extractor.run()
    extracted = _aggregate_extraction_results(extracted_results)

    _safe_write_json(raw_out, extracted, overwrite=cfg.overwrite)
    logger.info("Saved RAW extracted cases: %s", str(raw_out))

    curated_all: List[Dict[str, Any]] = []
    curated_usable: List[Dict[str, Any]] = []

    if cfg.do_curate:
        curator = CurateLiteratureCase(
            model_key=cfg.model_key,
            temperature=cfg.curate_temperature,
        )
        curated_all, curated_usable = curator.curate_all(extracted)

        _safe_write_json(curated_all_out, curated_all, overwrite=cfg.overwrite)
        _safe_write_json(curated_usable_out, curated_usable, overwrite=cfg.overwrite)

        logger.info("Saved curated ALL: %s", str(curated_all_out))
        logger.info("Saved curated USABLE: %s", str(curated_usable_out))
        logger.info("Counts (%s): total=%d usable=%d", stem, len(curated_all), len(curated_usable))

    return {
        "source": pdf_path,
        "raw_path": str(raw_out),
        "curated_all_path": str(curated_all_out) if cfg.do_curate else None,
        "curated_usable_path": str(curated_usable_out) if cfg.do_curate else None,
        "extracted": extracted,
        "curated_all": curated_all,
        "curated_usable": curated_usable,
    }


def run_on_extracted_json(extracted_cases_json_path: str, *, cfg: PipelineConfig) -> Dict[str, Any]:
    """
    Load ONE extracted JSON (no extraction), then optionally curate.
    Saves:
      - curated_cases/<stem>_<ts>_{all,usable}.json (if cfg.do_curate)
    Returns similar structure to run_on_pdf.
    """
    ts = cfg.run_timestamp or _ts()
    stem = Path(extracted_cases_json_path).stem

    _ensure_dir(cfg.curated_out_dir)

    curated_all_out = Path(cfg.curated_out_dir) / f"{stem}_{ts}_all.json"
    curated_usable_out = Path(cfg.curated_out_dir) / f"{stem}_{ts}_usable.json"

    with open(extracted_cases_json_path, "r", encoding="utf-8") as f:
        extracted = json.load(f)

    curated_all: List[Dict[str, Any]] = []
    curated_usable: List[Dict[str, Any]] = []

    if cfg.do_curate:
        curator = CurateLiteratureCase(
            model_key=cfg.model_key,
            temperature=cfg.curate_temperature,
        )
        curated_all, curated_usable = curator.curate_all(extracted)

        _safe_write_json(curated_all_out, curated_all, overwrite=cfg.overwrite)
        _safe_write_json(curated_usable_out, curated_usable, overwrite=cfg.overwrite)

        logger.info("Saved curated ALL: %s", str(curated_all_out))
        logger.info("Saved curated USABLE: %s", str(curated_usable_out))
        logger.info("Counts (%s): total=%d usable=%d", stem, len(curated_all), len(curated_usable))

    return {
        "source": extracted_cases_json_path,
        "raw_path": extracted_cases_json_path,  # already-extracted
        "curated_all_path": str(curated_all_out) if cfg.do_curate else None,
        "curated_usable_path": str(curated_usable_out) if cfg.do_curate else None,
        "extracted": extracted,
        "curated_all": curated_all,
        "curated_usable": curated_usable,
    }


def run_pipeline(*, cfg: PipelineConfig) -> List[Dict[str, Any]]:
    """
    Configurable entrypoint.

    Supported modes:
      cfg.input_kind="pdf"      cfg.input_path=<single pdf> OR a dir (we'll treat as single if file)
      cfg.input_kind="pdf_dir"  cfg.input_path=<docs folder>
      cfg.input_kind="json"     cfg.input_path=<single extracted json>
      cfg.input_kind="json_dir" cfg.input_path=<extracted_cases/raw_cases folder>
    """
    ts = cfg.run_timestamp or _ts()
    cfg = PipelineConfig(**{**cfg.__dict__, "run_timestamp": ts})

    results: List[Dict[str, Any]] = []

    if cfg.input_kind == "pdf":
        pdfs = _iter_pdfs(cfg.input_path)
        if len(pdfs) != 1:
            raise ValueError(f"input_kind='pdf' requires a single PDF file; got {len(pdfs)} from {cfg.input_path}")
        results.append(run_on_pdf(str(pdfs[0]), cfg=cfg))
        return results

    if cfg.input_kind == "pdf_dir":
        pdfs = _iter_pdfs(cfg.input_path)
        logger.info("Found %d PDFs under %s", len(pdfs), cfg.input_path)
        for p in pdfs:
            results.append(run_on_pdf(str(p), cfg=cfg))
        return results

    if cfg.input_kind == "json":
        jsons = _iter_jsons(cfg.input_path)
        if len(jsons) != 1:
            raise ValueError(f"input_kind='json' requires a single JSON file; got {len(jsons)} from {cfg.input_path}")
        results.append(run_on_extracted_json(str(jsons[0]), cfg=cfg))
        return results

    if cfg.input_kind == "json_dir":
        jsons = _iter_jsons(cfg.input_path)
        logger.info("Found %d extracted JSONs under %s", len(jsons), cfg.input_path)
        for p in jsons:
            results.append(run_on_extracted_json(str(p), cfg=cfg))
        return results

    raise ValueError(f"Unsupported input_kind: {cfg.input_kind}")


def main() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

    # ---- Examples: pick ONE by editing cfg ----

    # 1) single PDF: extract +/- curate
    # cfg = PipelineConfig(
    #     model_key="gpt-5-mini",
    #     input_kind="pdf",
    #     input_path=r"data/docs/100_cases_in_clinical_ethics_and_law.pdf", 
    #     do_curate=True,
    # )

    # 2) docs folder: iterate over all PDFs extract +/- curate
    cfg = PipelineConfig(
        input_kind="pdf_dir",
        input_path=r"data/docs",
        do_curate=True,
    )

    # 3) single extracted JSON: curate (no extraction)
    # cfg = PipelineConfig(
    #     input_kind="json",
    #     model_key="gpt-5-mini",# "gemini-2.5-flash-preview-09-2025"
    #     input_path=r"data\extracted_cases\raw_cases\medical_ethics_and_law_q_a_2025-12-21-13-17_raw.json",
    #     do_curate=True,
    # )

    # 4) raw_cases folder: iterate over all extracted JSONs and curate
    # cfg = PipelineConfig(
    #     input_kind="json_dir",
    #     input_path=r"data\extracted_cases\raw_cases",
    #     do_curate=True,
    # )

    results = run_pipeline(cfg=cfg)
    
    if cfg.do_curate and (cfg.input_kind == "json_dir" or cfg.input_kind == "pdf_dir"):
        unified_data: List[Dict[str, Any]] = []
        
        for result in results:
            source_path = result.get("source", "")
            curated_all = result.get("curated_all", [])
            
            source_filename = Path(source_path).stem if source_path else "Unknown"
            book_name = source_filename.replace("_", " ").title()
            
            for entry in curated_all:
                vals = entry.get("values", [])
                val1 = vals[0] if len(vals) > 0 else entry.get("value_1")
                val2 = vals[1] if len(vals) > 1 else entry.get("value_2")
                
                new_record = {
                    "scenario_type": entry.get("scenario_type"),
                    "value_1": val1,
                    "value_2": val2,
                    "case": entry.get("case") or entry.get("text") or entry.get("vignette", ""),
                    "reference": {
                        "source": book_name,
                        "start_page": entry.get("start_page"),
                        "end_page": entry.get("end_page")
                    }
                }
                unified_data.append(new_record)
            
            logger.info("Processed %d cases from: %s", len(curated_all), book_name)
        
        ts = cfg.run_timestamp or _ts()
        combined_output_path = Path(cfg.curated_out_dir) / f"all_pdfs_{ts}_combined.json"
        _safe_write_json(combined_output_path, unified_data, overwrite=cfg.overwrite)
        logger.info("Saved combined curated cases (%d total) to: %s", len(unified_data), str(combined_output_path))


if __name__ == "__main__":
    main()
 