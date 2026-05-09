from pathlib import Path


class FileParser:
    def __init__(self, semantic_memory=None):
        self.semantic = semantic_memory

    async def parse(self, file_path: str) -> str:
        """Detect file type, parse to text, optionally index to semantic memory."""
        path = Path(file_path)
        ext = path.suffix.lower()

        handlers = {
            ".pdf": self._parse_pdf,
            ".docx": self._parse_docx,
            ".csv": self._parse_csv,
            ".txt": self._parse_txt,
            ".md": self._parse_md,
        }

        handler = handlers.get(ext)
        if not handler:
            return f"Unsupported file type: {ext}"

        text = handler(str(path))

        if self.semantic and text:
            self.semantic.index(source=str(path), content=text)

        return text[:10000]

    def _parse_pdf(self, path: str) -> str:
        from .formats.pdf import parse
        return parse(path)

    def _parse_docx(self, path: str) -> str:
        from .formats.docx import parse
        return parse(path)

    def _parse_csv(self, path: str) -> str:
        from .formats.csv import parse
        return parse(path)

    def _parse_txt(self, path: str) -> str:
        from .formats.txt import parse
        return parse(path)

    def _parse_md(self, path: str) -> str:
        from .formats.md import parse
        return parse(path)

    def tool_schema(self) -> dict:
        return {
            "name": "file_parser",
            "description": "Parse a file (PDF, DOCX, CSV, TXT, MD) and return its text content",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to parse",
                    }
                },
                "required": ["file_path"],
            },
        }
