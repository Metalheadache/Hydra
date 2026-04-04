"""
PDF merge and split tools for Hydra agents.

Implements against pymupdf (fitz) which is the actual core dependency
for PDF handling in Hydra. Falls back to pypdf if pymupdf is unavailable.

Dependencies:
    pymupdf  (already in core deps — used by existing read_pdf)
    pypdf    (optional fallback)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from hydra_agents.models import ToolResult
from hydra_agents.tools._security import ensure_dir, safe_read_path, safe_write_path
from hydra_agents.tools.base import BaseTool

if TYPE_CHECKING:
    from hydra_agents.state_manager import StateManager

logger = structlog.get_logger(__name__)

_DEFAULT_OUTPUT_DIR = "./hydra_output"


def _parse_page_range(spec: str, max_pages: int) -> list[int]:
    """Parse '1-5', '1,3,5', '1-3,7,9-11' into 0-indexed page list."""
    indices = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start = max(0, int(start_s) - 1)
            end = min(int(end_s), max_pages)
            indices.extend(range(start, end))
        else:
            idx = int(part) - 1
            if 0 <= idx < max_pages:
                indices.append(idx)
    return indices


def _get_pdf_backend() -> str:
    """Detect which PDF library is available."""
    try:
        import fitz  # pymupdf  # noqa: F401
        return "pymupdf"
    except ImportError:
        pass
    try:
        import pypdf  # noqa: F401
        return "pypdf"
    except ImportError:
        pass
    return "none"


# ── pdf_merge ─────────────────────────────────────────────────────────────────


class PdfMergeTool(BaseTool):
    """Merge multiple PDF files into one."""

    name = "pdf_merge"
    description = (
        "Merge multiple PDF files into a single PDF. Supports page range "
        "selection per file and optional bookmark labels for each source."
    )
    parameters = {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to PDF file."},
                        "pages": {
                            "type": "string",
                            "description": "Page range: '1-5', '1,3,5', or '' for all. 1-indexed.",
                            "default": "",
                        },
                        "label": {
                            "type": "string",
                            "description": "Bookmark label for this section.",
                            "default": "",
                        },
                    },
                    "required": ["path"],
                },
                "description": "PDF files to merge, in order.",
            },
            "output_filename": {
                "type": "string",
                "description": "Output filename (e.g. 'merged.pdf').",
            },
            "add_bookmarks": {
                "type": "boolean",
                "description": "Add bookmarks for each source file. Default: true.",
                "default": True,
            },
        },
        "required": ["files", "output_filename"],
    }

    def __init__(
        self,
        output_dir: str = _DEFAULT_OUTPUT_DIR,
        state_manager: "StateManager | None" = None,
    ) -> None:
        self._output_dir = output_dir
        self._state_manager = state_manager

    async def execute(
        self,
        files: list[dict],
        output_filename: str,
        add_bookmarks: bool = True,
    ) -> ToolResult:
        backend = _get_pdf_backend()
        if backend == "none":
            return ToolResult(success=False, error="No PDF library found. Install pymupdf or pypdf.")

        try:
            output_dir = ensure_dir(self._output_dir)
            if not output_filename.endswith(".pdf"):
                output_filename += ".pdf"
            out_path = safe_write_path(output_dir, output_filename)
            if out_path is None:
                return ToolResult(success=False, error="Path traversal blocked")

            if backend == "pymupdf":
                result = await self._merge_pymupdf(files, out_path, add_bookmarks)
            else:
                result = await self._merge_pypdf(files, out_path, add_bookmarks)

            if self._state_manager is not None:
                await self._state_manager.register_file(output_filename, str(out_path))

            return result

        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:
            logger.error("pdf_merge_failed", error=str(exc))
            return ToolResult(success=False, error=f"PDF merge failed: {exc}")

    async def _merge_pymupdf(
        self, files: list[dict], out_path: Path, add_bookmarks: bool
    ) -> ToolResult:
        import fitz

        output_doc = fitz.open()
        sources = []
        total_pages = 0

        for file_spec in files:
            src_path = safe_read_path(file_spec["path"], allowed_roots=[str(Path(self._output_dir).resolve()), str(Path.cwd().resolve())])
            src_doc = fitz.open(str(src_path))
            page_range = file_spec.get("pages", "")
            label = file_spec.get("label", src_path.stem)

            if page_range:
                indices = _parse_page_range(page_range, len(src_doc))
            else:
                indices = list(range(len(src_doc)))

            bookmark_page = total_pages

            for idx in indices:
                output_doc.insert_pdf(src_doc, from_page=idx, to_page=idx)
                total_pages += 1

            if add_bookmarks and label:
                # pymupdf bookmark: [level, title, page, ...]
                toc = output_doc.get_toc()
                toc.append([1, label, bookmark_page + 1])
                output_doc.set_toc(toc)

            sources.append({"file": str(src_path), "pages_added": len(indices)})
            src_doc.close()

        output_doc.save(str(out_path))
        output_doc.close()

        logger.info("pdf_merge_success", output=str(out_path), total_pages=total_pages)
        return ToolResult(
            success=True,
            data={
                "output_path": str(out_path),
                "total_pages": total_pages,
                "sources": sources,
                "size_bytes": out_path.stat().st_size,
            },
        )

    async def _merge_pypdf(
        self, files: list[dict], out_path: Path, add_bookmarks: bool
    ) -> ToolResult:
        from pypdf import PdfReader, PdfWriter

        writer = PdfWriter()
        sources = []
        total_pages = 0

        for file_spec in files:
            src_path = safe_read_path(file_spec["path"], allowed_roots=[str(Path(self._output_dir).resolve()), str(Path.cwd().resolve())])
            reader = PdfReader(str(src_path))
            page_range = file_spec.get("pages", "")
            label = file_spec.get("label", src_path.stem)

            if page_range:
                indices = _parse_page_range(page_range, len(reader.pages))
            else:
                indices = list(range(len(reader.pages)))

            bookmark_page = total_pages
            for idx in indices:
                writer.add_page(reader.pages[idx])
                total_pages += 1

            if add_bookmarks and label:
                writer.add_outline_item(label, bookmark_page)

            sources.append({"file": str(src_path), "pages_added": len(indices)})

        with open(str(out_path), "wb") as f:
            writer.write(f)

        logger.info("pdf_merge_success", output=str(out_path), total_pages=total_pages)
        return ToolResult(
            success=True,
            data={
                "output_path": str(out_path),
                "total_pages": total_pages,
                "sources": sources,
                "size_bytes": out_path.stat().st_size,
            },
        )


# ── pdf_split ─────────────────────────────────────────────────────────────────


class PdfSplitTool(BaseTool):
    """Split a PDF into multiple files."""

    name = "pdf_split"
    description = (
        "Split a PDF into multiple files. Modes: 'pages' (extract specific "
        "pages), 'chunks' (split every N pages), 'each' (one PDF per page)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the PDF to split.",
            },
            "mode": {
                "type": "string",
                "enum": ["pages", "chunks", "each"],
                "description": "'pages': extract ranges. 'chunks': split every N pages. 'each': one file per page.",
            },
            "pages": {
                "type": "string",
                "description": "For 'pages' mode: range like '1-5' or '1,3,5-8'.",
                "default": "",
            },
            "chunk_size": {
                "type": "integer",
                "description": "For 'chunks' mode: pages per output file. Default: 10.",
                "default": 10,
            },
            "name_prefix": {
                "type": "string",
                "description": "Prefix for output filenames. Default: source filename stem.",
                "default": "",
            },
        },
        "required": ["file_path", "mode"],
    }

    def __init__(
        self,
        output_dir: str = _DEFAULT_OUTPUT_DIR,
        state_manager: "StateManager | None" = None,
    ) -> None:
        self._output_dir = output_dir
        self._state_manager = state_manager

    async def execute(
        self,
        file_path: str,
        mode: str,
        pages: str = "",
        chunk_size: int = 10,
        name_prefix: str = "",
    ) -> ToolResult:
        backend = _get_pdf_backend()
        if backend == "none":
            return ToolResult(success=False, error="No PDF library found. Install pymupdf or pypdf.")

        if mode == "chunks" and chunk_size < 1:
            return ToolResult(success=False, error=f"chunk_size must be >= 1, got {chunk_size}")

        try:
            src_path = safe_read_path(file_path, allowed_roots=[str(Path(self._output_dir).resolve()), str(Path.cwd().resolve())])
            output_dir = ensure_dir(self._output_dir)
            prefix = name_prefix or src_path.stem

            if backend == "pymupdf":
                result = await self._split_pymupdf(src_path, output_dir, mode, pages, chunk_size, prefix)
            else:
                result = await self._split_pypdf(src_path, output_dir, mode, pages, chunk_size, prefix)

            return result

        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:
            logger.error("pdf_split_failed", error=str(exc))
            return ToolResult(success=False, error=f"PDF split failed: {exc}")

    async def _split_pymupdf(
        self, src_path: Path, output_dir: Path, mode: str,
        pages: str, chunk_size: int, prefix: str,
    ) -> ToolResult:
        import fitz

        doc = fitz.open(str(src_path))
        total = len(doc)
        output_files = []

        if mode == "each":
            for i in range(total):
                out_doc = fitz.open()
                out_doc.insert_pdf(doc, from_page=i, to_page=i)
                fname = f"{prefix}_page_{i + 1}.pdf"
                out = safe_write_path(output_dir, fname)
                if out is None:
                    continue
                out_doc.save(str(out))
                out_doc.close()
                output_files.append(str(out))

        elif mode == "chunks":
            for start in range(0, total, chunk_size):
                end = min(start + chunk_size, total) - 1
                out_doc = fitz.open()
                out_doc.insert_pdf(doc, from_page=start, to_page=end)
                fname = f"{prefix}_pages_{start + 1}-{end + 1}.pdf"
                out = safe_write_path(output_dir, fname)
                if out is None:
                    continue
                out_doc.save(str(out))
                out_doc.close()
                output_files.append(str(out))

        elif mode == "pages":
            if not pages:
                doc.close()
                return ToolResult(success=False, error="'pages' parameter required for 'pages' mode")
            indices = _parse_page_range(pages, total)
            out_doc = fitz.open()
            for idx in indices:
                out_doc.insert_pdf(doc, from_page=idx, to_page=idx)
            fname = f"{prefix}_extracted.pdf"
            out = safe_write_path(output_dir, fname)
            if out is None:
                doc.close()
                return ToolResult(success=False, error="Path traversal blocked")
            out_doc.save(str(out))
            out_doc.close()
            output_files.append(str(out))

        doc.close()

        # Register output files
        if self._state_manager is not None:
            for fp in output_files:
                await self._state_manager.register_file(Path(fp).name, fp)

        logger.info("pdf_split_success", mode=mode, output_count=len(output_files))
        return ToolResult(
            success=True,
            data={
                "output_files": output_files,
                "file_count": len(output_files),
                "source_pages": total,
                "mode": mode,
            },
        )

    async def _split_pypdf(
        self, src_path: Path, output_dir: Path, mode: str,
        pages: str, chunk_size: int, prefix: str,
    ) -> ToolResult:
        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(str(src_path))
        total = len(reader.pages)
        output_files = []

        if mode == "each":
            for i in range(total):
                writer = PdfWriter()
                writer.add_page(reader.pages[i])
                fname = f"{prefix}_page_{i + 1}.pdf"
                out = safe_write_path(output_dir, fname)
                if out is None:
                    continue
                with open(str(out), "wb") as f:
                    writer.write(f)
                output_files.append(str(out))

        elif mode == "chunks":
            for start in range(0, total, chunk_size):
                end = min(start + chunk_size, total)
                writer = PdfWriter()
                for i in range(start, end):
                    writer.add_page(reader.pages[i])
                fname = f"{prefix}_pages_{start + 1}-{end}.pdf"
                out = safe_write_path(output_dir, fname)
                if out is None:
                    continue
                with open(str(out), "wb") as f:
                    writer.write(f)
                output_files.append(str(out))

        elif mode == "pages":
            if not pages:
                return ToolResult(success=False, error="'pages' parameter required for 'pages' mode")
            indices = _parse_page_range(pages, total)
            writer = PdfWriter()
            for idx in indices:
                writer.add_page(reader.pages[idx])
            fname = f"{prefix}_extracted.pdf"
            out = safe_write_path(output_dir, fname)
            if out is None:
                return ToolResult(success=False, error="Path traversal blocked")
            with open(str(out), "wb") as f:
                writer.write(f)
            output_files.append(str(out))

        if self._state_manager is not None:
            for fp in output_files:
                await self._state_manager.register_file(Path(fp).name, fp)

        logger.info("pdf_split_success", mode=mode, output_count=len(output_files))
        return ToolResult(
            success=True,
            data={
                "output_files": output_files,
                "file_count": len(output_files),
                "source_pages": total,
                "mode": mode,
            },
        )
