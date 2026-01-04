import os
import json
from abc import ABC, abstractmethod
from typing import Optional

class FileHandler(ABC):
    @abstractmethod
    def extract_text(self, path: str) -> str:
        pass
    
    @property
    @abstractmethod
    def file_type(self) -> str:
        pass

class PDFHandler(FileHandler):
    def extract_text(self, path: str) -> str:
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(path)
            text = []
            for page in doc:
                text.append(page.get_text())
            full_text = "\n".join(text)
            if not full_text.strip():
                raise ValueError("PDF contains no text (might be scanned images).")
            return full_text
        except ImportError:
            raise ImportError("PyMuPDF (fitz) not installed.")
        except Exception as e:
            if "PDF contains no text" in str(e): raise e
            raise ValueError(f"PDF Read Error: {str(e)}")
    
    @property
    def file_type(self) -> str:
        return "pdf"

class DocxHandler(FileHandler):
    def extract_text(self, path: str) -> str:
        try:
            import docx
            doc = docx.Document(path)
            text = "\n".join([p.text for p in doc.paragraphs])
            if not text.strip():
                raise ValueError("Docx appears empty.")
            return text
        except ImportError:
            raise ImportError("python-docx not installed.")
        except Exception as e:
            if "Docx appears empty" in str(e): raise e
            raise ValueError(f"Docx Read Error: {str(e)}")
    
    @property
    def file_type(self) -> str:
        return "docx"

class TextHandler(FileHandler):
    def extract_text(self, path: str) -> str:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    @property
    def file_type(self) -> str:
        return "text"

class BinaryDocHandler(FileHandler):
    def extract_text(self, path: str) -> str:
        raise ValueError(".doc files (Word 97-2003) are not supported. Please save as .docx and try again.")

    @property
    def file_type(self) -> str:
        return "doc"

def get_handler_for_file(path: str) -> Optional[FileHandler]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return PDFHandler()
    elif ext == ".docx":
        return DocxHandler()
    elif ext == ".doc":
        return BinaryDocHandler()
    elif ext in [".txt", ".md", ".py", ".js", ".json", ".csv"]:
        return TextHandler()
    return None
