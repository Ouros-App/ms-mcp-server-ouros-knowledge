import argparse
import hashlib
import json
import uuid
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from docx import Document as DocxDocument
from langchain_core.documents import Document
from pypdf import PdfReader

from app.core.config import settings
from app.services.knowledge import get_qdrant_client, get_vector_store, qdrant_status

DEFAULT_DOCS_DIR = Path("docs")
MANIFEST_NAME = ".qdrant-manifest.json"
SUPPORTED_EXTENSIONS = {
    ".csv",
    ".docx",
    ".html",
    ".htm",
    ".json",
    ".md",
    ".pdf",
    ".txt",
}


def split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split text into bounded, overlapping chunks."""
    if chunk_size <= 0:
        raise ValueError("chunk-size deve ser maior que zero")
    if not 0 <= chunk_overlap < chunk_size:
        raise ValueError("chunk-overlap deve estar entre zero e chunk-size - 1")

    text = "\n".join(line.rstrip(" \t") for line in text.splitlines()).strip()
    chunks: list[str] = []
    start = 0
    while start < len(text):
        hard_end = min(start + chunk_size, len(text))
        end = hard_end
        if hard_end < len(text):
            break_at = max(
                text.rfind("\n", start, hard_end), text.rfind(" ", start, hard_end)
            )
            if break_at > start + chunk_size // 2:
                end = break_at

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - chunk_overlap, start + 1)
    return chunks


def discover_files(
    paths: Iterable[Path],
    excluded_paths: Iterable[Path] = (),
) -> list[Path]:
    """Find supported files while excluding manifests and configured paths."""
    files: set[Path] = set()
    excluded = {path.expanduser().resolve() for path in excluded_paths}
    for path in paths:
        path = path.expanduser()
        if not path.exists():
            raise FileNotFoundError(f"caminho não encontrado: {path}")
        if path.resolve() in excluded:
            continue
        if path.is_file():
            if path.name == MANIFEST_NAME:
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                raise ValueError(f"formato não suportado: {path.suffix or path.name}")
            files.add(path.resolve())
            continue
        files.update(
            candidate.resolve()
            for candidate in path.rglob("*")
            if candidate.is_file()
            and candidate.name != MANIFEST_NAME
            and candidate.resolve() not in excluded
            and candidate.suffix.lower() in SUPPORTED_EXTENSIONS
        )
    return sorted(files)


def file_hash(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict:
    """Load an ingestion manifest or return its empty initial shape."""
    if not path.exists():
        return {"version": 1, "files": {}}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"manifesto inválido: {path}") from error
    if not isinstance(manifest, dict) or not isinstance(
        manifest.get("files", {}), dict
    ):
        raise TypeError(f"manifesto inválido: {path}")
    manifest.setdefault("files", {})
    return manifest


def save_manifest(path: Path, manifest: dict, allowed_root: Path) -> None:
    """Persist an ingestion manifest as UTF-8 JSON."""
    path = path.expanduser().resolve()
    allowed_root = allowed_root.expanduser().resolve()
    if not path.is_relative_to(allowed_root):
        raise ValueError("manifest deve ficar dentro do diretório processado")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(  # NOSONAR - path is constrained to allowed_root above.
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def manifest_key(path: Path, docs_dir: Path) -> str:
    """Return the stable manifest key for a discovered file."""
    try:
        return path.relative_to(docs_dir).as_posix()
    except ValueError:
        return path.as_posix()


def extract_file(path: Path) -> list[Document]:
    """Extract LangChain documents from a supported file."""
    metadata = {
        "source": str(path),
        "file_name": path.name,
        "file_type": path.suffix.lower().lstrip("."),
    }
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        documents = []
        for page_number, page in enumerate(PdfReader(str(path)).pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                documents.append(
                    Document(
                        page_content=text, metadata={**metadata, "page": page_number}
                    )
                )
        return documents

    if suffix == ".docx":
        document = DocxDocument(str(path))
        blocks = [
            paragraph.text.strip()
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        ]
        blocks.extend(
            " | ".join(cell.text.strip() for cell in row.cells)
            for table in document.tables
            for row in table.rows
            if any(cell.text.strip() for cell in row.cells)
        )
        text = "\n".join(blocks)
    else:
        text = path.read_text(encoding="utf-8", errors="ignore")

    return [Document(page_content=text, metadata=metadata)] if text.strip() else []


def prepare_documents(
    path: Path, chunk_size: int, chunk_overlap: int
) -> list[Document]:
    """Extract and chunk one source file."""
    chunks: list[Document] = []
    for source_document in extract_file(path):
        for chunk_index, text in enumerate(
            split_text(source_document.page_content, chunk_size, chunk_overlap)
        ):
            chunks.append(
                Document(
                    page_content=text,
                    metadata={**source_document.metadata, "chunk_index": chunk_index},
                )
            )
    return chunks


def document_id(document: Document) -> str:
    """Return a deterministic point ID for a document chunk."""
    source = document.metadata["source"]
    page = document.metadata.get("page", "")
    chunk_index = document.metadata["chunk_index"]
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}:{page}:{chunk_index}"))


def _manifest_key_in_scope(
    key: str,
    docs_dir: Path,
    paths: Iterable[Path],
) -> bool:
    """Check whether a manifest entry belongs to a processed path scope."""
    normalized_key = key.replace("\\", "/")
    key_parts = PurePosixPath(normalized_key).parts
    if ".." in key_parts:
        return False
    is_absolute = PurePosixPath(normalized_key).is_absolute() or (
        len(normalized_key) > 2 and normalized_key[1] == ":"
    )
    docs_prefix = docs_dir.resolve().as_posix().rstrip("/")
    candidate = (
        normalized_key.rstrip("/")
        if is_absolute
        else f"{docs_prefix}/{normalized_key.lstrip('/')}"
    )
    for path in paths:
        resolved_path = path.expanduser().resolve()
        resolved = resolved_path.as_posix().rstrip("/")
        if resolved_path.is_dir() and (
            candidate == resolved or candidate.startswith(f"{resolved}/")
        ):
            return True
        if candidate == resolved:
            return True
    return False


def _manifest_location(path: Path, paths: Iterable[Path]) -> tuple[Path, Path]:
    """Validate a manifest location and return it with its trusted root."""
    resolved = path.expanduser().resolve()
    for source in paths:
        root = source.expanduser().resolve()
        if root.is_file():
            root = root.parent
        if resolved == root or root in resolved.parents:
            return resolved, root
    raise ValueError("manifest deve ficar dentro do diretório processado")


def _collect_pending(
    files: list[Path],
    manifest_files: dict,
    chunk_size: int,
    chunk_overlap: int,
    docs_dir: Path,
) -> list[tuple[Path, str, list[Document], dict]]:
    """Prepare files whose content or ingestion settings changed."""
    pending: list[tuple[Path, str, list[Document], dict]] = []
    for path in files:
        key = manifest_key(path, docs_dir)
        digest = file_hash(path)
        previous = manifest_files.get(key, {})
        changed = (
            previous.get("sha256") != digest
            or previous.get("collection") != settings.QDRANT_COLLECTION_NAME
            or previous.get("embedding_model") != settings.NVIDIA_EMBEDDING_MODEL
            or previous.get("chunk_size") != chunk_size
            or previous.get("chunk_overlap") != chunk_overlap
        )
        if not changed:
            print(f"IGNORADO sem alteração: {key}")
            continue

        documents = prepare_documents(path, chunk_size, chunk_overlap)
        ids = [document_id(document) for document in documents]
        record = {
            "sha256": digest,
            "collection": settings.QDRANT_COLLECTION_NAME,
            "embedding_model": settings.NVIDIA_EMBEDDING_MODEL,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "chunk_count": len(documents),
            "ids": ids,
        }
        pending.append((path, key, documents, record))
        print(f"ALTERADO: {key} -> {len(documents)} chunks")
    return pending


def _qdrant_resources(
    dry_run: bool,
    has_work: bool,
    has_pending: bool,
) -> tuple[object | None, object | None]:
    """Open Qdrant resources only when a real synchronization is needed."""
    if dry_run or not has_work:
        return None, None
    status = qdrant_status()
    if not status["exists"]:
        raise RuntimeError(
            f"coleção Qdrant não encontrada: {status['collection']} ({status['error']})"
        )
    client = get_qdrant_client()
    return client, get_vector_store() if has_pending else None


def _remove_stale(
    stale_keys: list[str],
    manifest_files: dict,
    client: object | None,
    dry_run: bool,
) -> None:
    """Delete Qdrant points and manifest records for missing source files."""
    for key in stale_keys:
        stale_ids = manifest_files[key].get("ids", [])
        if dry_run:
            print(f"REMOVERIA: {key} -> {len(stale_ids)} chunks")
            continue
        if stale_ids:
            client.delete(  # type: ignore[union-attr]
                collection_name=settings.QDRANT_COLLECTION_NAME,
                points_selector=stale_ids,
                wait=True,
            )
        del manifest_files[key]
        print(f"REMOVIDO: {key} -> {len(stale_ids)} chunks")


def _upload_pending(
    pending: list[tuple[Path, str, list[Document], dict]],
    manifest: dict,
    manifest_path: Path,
    batch_size: int,
    store: object | None,
    client: object | None,
    manifest_root: Path,
) -> int:
    """Upload changed chunks and remove superseded point IDs."""
    total = 0
    for _path, key, documents, record in pending:
        for start in range(0, len(documents), batch_size):
            batch = documents[start : start + batch_size]
            store.add_documents(  # type: ignore[union-attr]
                batch, ids=[document_id(document) for document in batch]
            )
            total += len(batch)

        previous_ids = set(manifest["files"].get(key, {}).get("ids", []))
        stale_ids = sorted(previous_ids - set(record["ids"]))
        if stale_ids:
            client.delete(  # type: ignore[union-attr]
                collection_name=settings.QDRANT_COLLECTION_NAME,
                points_selector=stale_ids,
                wait=True,
            )
        manifest["files"][key] = record
        save_manifest(manifest_path, manifest, manifest_root)
    return total


def ingest(
    paths: list[Path],
    chunk_size: int,
    chunk_overlap: int,
    batch_size: int,
    dry_run: bool,
    manifest_path: Path,
) -> None:
    """Synchronize changed and removed documents with the Qdrant collection."""
    docs_dir = DEFAULT_DOCS_DIR.resolve()
    manifest_path, manifest_root = _manifest_location(manifest_path, paths)
    files = discover_files(paths, excluded_paths=[manifest_path])
    manifest = load_manifest(manifest_path)
    manifest["collection"] = settings.QDRANT_COLLECTION_NAME
    manifest["embedding_model"] = settings.NVIDIA_EMBEDDING_MODEL
    manifest["chunk_size"] = chunk_size
    manifest["chunk_overlap"] = chunk_overlap
    discovered_keys = {manifest_key(path, docs_dir) for path in files}
    stale_keys = sorted(
        key
        for key in manifest["files"]
        if key not in discovered_keys and _manifest_key_in_scope(key, docs_dir, paths)
    )
    pending = _collect_pending(
        files, manifest["files"], chunk_size, chunk_overlap, docs_dir
    )

    if not files and not stale_keys:
        print("Nenhum arquivo suportado encontrado.")
        return

    client, store = _qdrant_resources(
        dry_run, bool(pending or stale_keys), bool(pending)
    )
    _remove_stale(stale_keys, manifest["files"], client, dry_run)

    if stale_keys and not dry_run:
        save_manifest(manifest_path, manifest, manifest_root)

    if not pending:
        print("Nenhuma alteração para enviar.")
        return

    total = (
        0
        if dry_run
        else _upload_pending(
            pending, manifest, manifest_path, batch_size, store, client, manifest_root
        )
    )

    if dry_run:
        print("Dry-run concluído; nada foi enviado ao Qdrant.")
    else:
        print(
            f"Upload concluído: {total} chunks enviados para {store.collection_name}."
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the ingestion CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Embeddar e enviar arquivos para o Qdrant."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest_parser = subparsers.add_parser(
        "ingest", help="processa arquivos e envia os chunks"
    )
    ingest_parser.add_argument(
        "paths", nargs="*", type=Path, help="arquivos ou diretórios (padrão: ./docs)"
    )
    ingest_parser.add_argument("--chunk-size", type=int, default=1000)
    ingest_parser.add_argument("--chunk-overlap", type=int, default=150)
    ingest_parser.add_argument("--batch-size", type=int, default=32)
    ingest_parser.add_argument(
        "--manifest", type=Path, default=DEFAULT_DOCS_DIR / MANIFEST_NAME
    )
    ingest_parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    """Run the ingestion CLI and convert expected errors to exit messages."""
    args = build_parser().parse_args()
    if args.command == "ingest":
        if args.batch_size <= 0:
            raise SystemExit("batch-size deve ser maior que zero")
        try:
            ingest(
                args.paths or [DEFAULT_DOCS_DIR],
                args.chunk_size,
                args.chunk_overlap,
                args.batch_size,
                args.dry_run,
                args.manifest,
            )
            return 0
        except (FileNotFoundError, TypeError, ValueError, RuntimeError) as error:
            raise SystemExit(f"Erro: {error}") from error
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
