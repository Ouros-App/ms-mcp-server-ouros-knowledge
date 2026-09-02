import base64
import binascii
import json
import zipfile
from io import BytesIO
from typing import Any
from urllib.request import Request, urlopen

from pypdf import PdfReader

from app.core.config import settings

MAX_FILE_BYTES = 8 * 1024 * 1024
ALLOWED_TYPES = {"application/pdf", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def _xlsx_to_markdown(content: bytes) -> str:
    """Convert workbook cells into a bounded Markdown document."""
    try:
        from openpyxl import load_workbook
    except ImportError as error:
        raise RuntimeError("suporte XLSX não está instalado") from error
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    sections: list[str] = []
    for sheet in workbook.worksheets:
        rows = [["" if value is None else str(value) for value in row]
                for row in sheet.iter_rows(values_only=True)]
        rows = [row for row in rows if any(cell.strip() for cell in row)]
        if not rows:
            continue
        width = max(len(row) for row in rows)
        normalized = [row + [""] * (width - len(row)) for row in rows]
        sections.append(f"## Planilha: {sheet.title}\n")
        sections.append("| " + " | ".join(normalized[0]) + " |\n")
        sections.append("| " + " | ".join(["---"] * width) + " |\n")
        sections.extend("| " + " | ".join(row) + " |\n" for row in normalized[1:])
    return "\n".join(sections)


def _pdf_to_markdown(content: bytes) -> str:
    """Extract text from a text-based PDF into Markdown."""
    reader = PdfReader(BytesIO(content))
    return "\n\n".join(
        f"## Página {index}\n\n{page.extract_text() or ''}"
        for index, page in enumerate(reader.pages, start=1)
    )


def file_to_markdown(filename: str, content_type: str, encoded_file: str) -> str:
    """Decode and convert one supported PDF/XLSX upload to Markdown."""
    if content_type not in ALLOWED_TYPES:
        raise ValueError("tipo de arquivo não suportado; use PDF ou XLSX")
    try:
        content = base64.b64decode(encoded_file, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("arquivo deve ser base64 válido") from error
    if not content or len(content) > MAX_FILE_BYTES:
        raise ValueError("arquivo vazio ou maior que 8 MiB")
    if content_type == "application/pdf":
        if not content.startswith(b"%PDF"):
            raise ValueError("assinatura de PDF inválida")
        markdown = _pdf_to_markdown(content)
    else:
        if not zipfile.is_zipfile(BytesIO(content)):
            raise ValueError("assinatura de XLSX inválida")
        markdown = _xlsx_to_markdown(content)
    if not markdown.strip():
        raise ValueError("não foi possível extrair texto do arquivo")
    return markdown[: settings.IMPORT_MARKDOWN_MAX_CHARS]


def extract_resource_records(markdown: str, source_name: str) -> dict[str, Any]:
    """Ask an NVIDIA NIM to extract canonical records without performing writes."""
    if not settings.NVIDIA_API_KEY or not settings.NVIDIA_NIM_URL:
        raise RuntimeError("NVIDIA NIM não está configurado")
    prompt = (
        "Extraia somente registros históricos de água e energia deste documento. "
        "Responda JSON com a chave records, usando exatamente os campos "
        "resource_type, farm_id, registration_date, start_hydrometer, "
        "end_hydrometer, energy_consumption, source_row e confidence. "
        "Não invente valores; use null quando ausente. Documento: " + source_name
    )
    payload = {"model": settings.NVIDIA_NIM_MODEL, "temperature": 0,
               "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": prompt},
                            {"role": "user", "content": markdown}]}
    request = Request(settings.NVIDIA_NIM_URL, data=json.dumps(payload).encode(),
                      headers={"Authorization": f"Bearer {settings.NVIDIA_API_KEY}",
                               "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=settings.NVIDIA_NIM_TIMEOUT) as response:
            body = json.loads(response.read())
        content = body["choices"][0]["message"]["content"]
        result = json.loads(content) if isinstance(content, str) else content
        records = result.get("records")
        if not isinstance(records, list):
            raise ValueError("NIM não retornou uma lista de records")
        return {"source_name": source_name, "records": records, "preview": True}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("resposta inválida do NVIDIA NIM") from error
