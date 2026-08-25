import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.cli import (
    MANIFEST_NAME,
    build_parser,
    discover_files,
    document_id,
    extract_file,
    file_hash,
    ingest,
    load_manifest,
    manifest_key,
    prepare_documents,
    save_manifest,
    split_text,
)


class FakeQdrantClient:
    def __init__(self) -> None:
        self.deleted: list[dict] = []

    def delete(self, **kwargs: object) -> None:
        self.deleted.append(kwargs)


class FakeVectorStore:
    collection_name = "test_collection"

    def __init__(self) -> None:
        self.added: list[tuple[list, list[str]]] = []

    def add_documents(self, documents: list, ids: list[str]) -> None:
        self.added.append((documents, ids))


class CliTests(unittest.TestCase):
    def test_text_and_file_helpers(self) -> None:
        self.assertEqual(
            split_text("one two three", 7, 2), ["one two", "wo thre", "ree"]
        )
        with self.assertRaises(ValueError):
            split_text("text", 0, 0)
        with self.assertRaises(ValueError):
            split_text("text", 3, 3)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "note.txt"
            source.write_text("conteúdo do documento", encoding="utf-8")
            self.assertEqual(len(extract_file(source)), 1)
            chunks = prepare_documents(source, 100, 10)
            self.assertEqual(len(chunks), 1)
            self.assertRegex(document_id(chunks[0]), r"^[0-9a-f-]{36}$")
            self.assertEqual(len(file_hash(source)), 64)
            self.assertEqual(manifest_key(source.resolve(), root.resolve()), "note.txt")

    def test_discover_files_excludes_custom_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "custom-manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            document = root / "guide.md"
            document.write_text("guide", encoding="utf-8")

            files = discover_files([root], excluded_paths=[manifest])

            self.assertEqual(files, [document.resolve()])
            self.assertNotIn(manifest.resolve(), files)

    def test_manifest_round_trip_and_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            manifest = {"version": 1, "files": {"a.txt": {"ids": ["1"]}}}
            save_manifest(path, manifest, Path(directory))
            self.assertEqual(load_manifest(path), manifest)
            with self.assertRaises(ValueError):
                save_manifest(
                    Path(directory).parent / "outside.json", manifest, Path(directory)
                )
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                load_manifest(path)
            path.write_text(json.dumps([]), encoding="utf-8")
            with self.assertRaises(TypeError):
                load_manifest(path)

    def test_ingest_dry_run_reprocesses_old_chunk_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "guide.md"
            source.write_text("guide content", encoding="utf-8")
            manifest_path = root / MANIFEST_NAME
            save_manifest(
                manifest_path,
                {
                    "files": {
                        str(source.resolve()): {
                            "sha256": file_hash(source),
                            "collection": "test_collection",
                            "embedding_model": "test-model",
                            "chunk_size": 10,
                            "chunk_overlap": 2,
                        }
                    }
                },
                root,
            )

            with (
                patch("app.cli.settings.QDRANT_COLLECTION_NAME", "test_collection"),
                patch("app.cli.settings.NVIDIA_EMBEDDING_MODEL", "test-model"),
            ):
                self.assertIsNone(ingest([root], 20, 2, 2, True, manifest_path))

    @patch(
        "app.cli.qdrant_status",
        return_value={"exists": True, "collection": "test_collection"},
    )
    def test_ingest_removes_stale_points_and_uploads_changes(self, _status) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "guide.md"
            source.write_text("guide content", encoding="utf-8")
            stale = (root / "removed.md").resolve()
            manifest_path = root / MANIFEST_NAME
            save_manifest(
                manifest_path,
                {
                    "files": {
                        str(stale): {
                            "ids": ["stale-point"],
                        }
                    }
                },
                root,
            )
            client = FakeQdrantClient()
            store = FakeVectorStore()
            with (
                patch("app.cli.settings.QDRANT_COLLECTION_NAME", "test_collection"),
                patch("app.cli.settings.NVIDIA_EMBEDDING_MODEL", "test-model"),
                patch("app.cli.get_qdrant_client", return_value=client),
                patch("app.cli.get_vector_store", return_value=store),
            ):
                self.assertIsNone(ingest([root], 20, 2, 2, False, manifest_path))

            self.assertEqual(len(store.added), 1)
            self.assertEqual(client.deleted[0]["points_selector"], ["stale-point"])
            self.assertNotIn(str(stale), load_manifest(manifest_path)["files"])

    def test_parser_accepts_ingest_options(self) -> None:
        args = build_parser().parse_args(["ingest", "docs", "--dry-run"])
        self.assertTrue(args.dry_run)
        self.assertEqual(args.paths, [Path("docs")])


if __name__ == "__main__":
    unittest.main()
