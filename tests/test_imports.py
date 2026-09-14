import base64
import unittest
from io import BytesIO
from unittest.mock import patch

from openpyxl import Workbook

from app.services.imports import file_to_markdown


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
            "historico.xlsx",
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
                "historico.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                self._xlsx([["data", "consumo"], ["2025-01-01", "12"]]),
            )

    def test_rejects_invalid_xlsx_signature(self) -> None:
        encoded = base64.b64encode(b"not-xlsx").decode()
        with self.assertRaisesRegex(ValueError, "assinatura de XLSX"):
            file_to_markdown(
                "historico.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                encoded,
            )
