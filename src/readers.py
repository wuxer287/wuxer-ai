from pathlib import Path
from pypdf import PdfReader
from consts import MAX_PDF_PAGES

def readFile(file_path: Path) -> str:
    if file_path.suffix == ".md":
        return file_path.read_text(encoding="utf-8")
    else:
        reader = PdfReader(file_path)
        text = ""

        for page in reader.pages:
            text += page.extract_text()

        return text

def validateFile(file_path: Path) -> None:
    if file_path.stat().st_size == 0:
        raise ValueError("Il file è vuoto")

    with open(file_path, "rb") as f:
        head = f.read(1024)

    if file_path.suffix == ".pdf":
        if b"%PDF-" not in head:
            raise ValueError("Non è un PDF valido")

        try:
            reader = PdfReader(file_path)
            encrypted = reader.is_encrypted
        except Exception:
            raise ValueError("Il PDF è danneggiato o non leggibile")

        if encrypted:
            raise ValueError("Il PDF è protetto da password")

        try:
            pages = len(reader.pages)
        except Exception:
            raise ValueError("Il PDF è danneggiato o non leggibile")

        if pages > MAX_PDF_PAGES:
            raise ValueError(f"Il PDF ha più di {MAX_PDF_PAGES} pagine")
    else:
        if b"\0" in head:
            raise ValueError("Non è un file di testo")

        try:
            file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ValueError("Il file deve essere codificato in UTF-8")
