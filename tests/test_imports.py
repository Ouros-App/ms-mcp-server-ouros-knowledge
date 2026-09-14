import base64
import json
import unittest
from io import BytesIO
from typing import Self
from unittest.mock import patch

from openpyxl import Workbook

from app.services.imports import extract_resource_records, file_to_markdown


class FakeResponse:
    def __init__(self, body: dict[str, object]) -> None:
        self.body = body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.body).encode()


class ImportTests(unittest.TestCase):
    def _xlsx(self, rows: list[list[str]]) -> str:
        workbook = Workbook()
        sheet = workbook.active
        for row in rows:
            sheet.append(row)
        buffer = BytesIO()
        workbook.save(buffer)
        return base64.b64encode(buffer.getvalue()).decode()

    def test_converts_xlsx_incrementally(self) -> None:
        markdown = file_to_markdown(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            self._xlsx([["data", "consumo"], ["2025-01-01", "12"]]),
        )
        self.assertIn("2025-01-01", markdown)

    def test_rejects_markdown_overflow(self) -> None:
        with (
            patch("app.services.imports.settings.IMPORT_MARKDOWN_MAX_CHARS", 10),
            self.assertRaisesRegex(ValueError, "excede o limite"),
        ):
            file_to_markdown(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                self._xlsx([["data", "consumo"], ["2025-01-01", "12"]]),
            )

    def test_rejects_invalid_xlsx_signature(self) -> None:
        encoded = base64.b64encode(b"not-xlsx").decode()
        with self.assertRaisesRegex(ValueError, "assinatura de XLSX"):
            file_to_markdown(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                encoded,
            )

    def test_rejects_invalid_content_and_base64(self) -> None:
        with self.assertRaisesRegex(ValueError, "tipo de arquivo"):
            file_to_markdown("text/plain", "aA==")
        with self.assertRaisesRegex(ValueError, "base64"):
            file_to_markdown("application/pdf", "not-base64")
        with self.assertRaisesRegex(ValueError, "assinatura de PDF"):
            file_to_markdown("application/pdf", base64.b64encode(b"not-pdf").decode())

    def test_extracts_records_from_nim(self) -> None:
        body = {"choices": [{"message": {"content": json.dumps({"records": []})}}]}
        response = FakeResponse(body)
        with (
            patch("app.services.imports.settings.NVIDIA_API_KEY", "token"),
            patch("app.services.imports.settings.NVIDIA_NIM_URL", "https://nim"),
            patch("app.services.imports.urlopen", return_value=response),
        ):
            result = extract_resource_records("# documento", "historico.xlsx")
        self.assertEqual(result["records"], [])

    def test_rejects_invalid_nim_records(self) -> None:
        body = {"choices": [{"message": {"content": json.dumps({"records": {}})}}]}
        response = FakeResponse(body)
        with (
            patch("app.services.imports.settings.NVIDIA_API_KEY", "token"),
            patch("app.services.imports.settings.NVIDIA_NIM_URL", "https://nim"),
            patch("app.services.imports.urlopen", return_value=response),
            self.assertRaisesRegex(RuntimeError, "resposta inválida"),
        ):
            extract_resource_records("# documento", "historico.xlsx")

    def test_rejects_xlsx_expansion_limits(self) -> None:
        encoded = self._xlsx([["data"], ["2025-01-01"]])
        cases = (
            ("MAX_XLSX_UNCOMPRESSED_BYTES", "descompactado"),
            ("MAX_XLSX_COMPRESSION_RATIO", "compressão"),
            ("MAX_XLSX_ROWS", "linhas"),
            ("MAX_XLSX_CELLS", "células"),
        )
        for constant, message in cases:
            with self.subTest(constant=constant), patch(
                f"app.services.imports.{constant}", 0
            ), self.assertRaisesRegex(ValueError, message):
                file_to_markdown(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    encoded,
                )
