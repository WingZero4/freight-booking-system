"""
File parsers for the LLM-powered import feature.

Each parser extracts text content from an uploaded file in a format
suitable for sending to the Claude API for field mapping.
"""
import csv
import io
import logging
import tempfile

logger = logging.getLogger(__name__)

MAX_ROWS = 500
MAX_CHARS = 50000


class FileParseError(Exception):
    """Raised when a file cannot be parsed."""
    pass


def parse_csv(uploaded_file) -> str:
    """Parse a CSV file into a pipe-delimited text table."""
    try:
        # Try UTF-8 first, then Latin-1
        uploaded_file.seek(0)
        raw = uploaded_file.read()
        try:
            text = raw.decode('utf-8-sig')
        except (UnicodeDecodeError, AttributeError):
            try:
                text = raw.decode('latin-1')
            except AttributeError:
                text = raw if isinstance(raw, str) else str(raw)

        reader = csv.reader(io.StringIO(text))
        rows = []
        for i, row in enumerate(reader):
            if i >= MAX_ROWS + 1:  # +1 for header
                break
            rows.append(row)

        if not rows:
            raise FileParseError('CSV file is empty.')

        # Format as pipe-delimited table
        lines = []
        for i, row in enumerate(rows):
            line = ' | '.join(cell.strip() for cell in row)
            lines.append(line)
            if i == 0:
                lines.append('---')

        result = '\n'.join(lines)
        return result[:MAX_CHARS]

    except FileParseError:
        raise
    except Exception as e:
        raise FileParseError(f'Failed to parse CSV: {e}')


def parse_xlsx(uploaded_file) -> str:
    """Parse an Excel file into a pipe-delimited text table."""
    try:
        import openpyxl

        uploaded_file.seek(0)
        wb = openpyxl.load_workbook(uploaded_file, read_only=True, data_only=True)
        ws = wb.active

        if ws is None:
            raise FileParseError('Excel file has no worksheets.')

        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= MAX_ROWS + 1:
                break
            # Convert cell values to strings
            cells = []
            for cell in row:
                if cell is None:
                    cells.append('')
                elif hasattr(cell, 'strftime'):
                    cells.append(cell.strftime('%Y-%m-%d'))
                else:
                    cells.append(str(cell))
            rows.append(cells)

        wb.close()

        if not rows:
            raise FileParseError('Excel file is empty.')

        # Skip fully empty rows
        rows = [r for r in rows if any(c.strip() for c in r)]

        if not rows:
            raise FileParseError('Excel file has no data.')

        # Format as pipe-delimited table
        lines = []
        for i, row in enumerate(rows):
            line = ' | '.join(cell.strip() for cell in row)
            lines.append(line)
            if i == 0:
                lines.append('---')

        result = '\n'.join(lines)
        return result[:MAX_CHARS]

    except FileParseError:
        raise
    except Exception as e:
        raise FileParseError(f'Failed to parse Excel file: {e}')


def parse_pdf(uploaded_file) -> str:
    """Parse a PDF file, extracting text and tables."""
    import os

    try:
        import pdfplumber

        uploaded_file.seek(0)

        # pdfplumber needs a file path or file-like object
        # Write to temp file since Django's UploadedFile may not support all ops
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            for chunk in uploaded_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            parts = []

            with pdfplumber.open(tmp_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    if page_num >= 20:  # Limit pages
                        parts.append(f'\n[... truncated after {page_num} pages ...]')
                        break

                    # Extract tables first (more structured)
                    tables = page.extract_tables()
                    if tables:
                        for table in tables:
                            for row in table:
                                if row:
                                    cells = [str(c).strip() if c else '' for c in row]
                                    parts.append(' | '.join(cells))
                            parts.append('')  # blank line between tables
                    else:
                        # Fall back to text extraction
                        text = page.extract_text()
                        if text:
                            parts.append(text)

                    parts.append('')  # Page separator

            result = '\n'.join(parts).strip()

            if not result:
                raise FileParseError(
                    'Could not extract text from PDF. '
                    'Scanned/image-based PDFs are not supported yet.'
                )

            return result[:MAX_CHARS]
        finally:
            # Always clean up temp file
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    except FileParseError:
        raise
    except Exception as e:
        raise FileParseError(f'Failed to parse PDF: {e}')


def parse_file(uploaded_file, filename: str) -> str:
    """Route to the correct parser based on file extension."""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    if ext == 'csv':
        return parse_csv(uploaded_file)
    elif ext == 'xlsx':
        return parse_xlsx(uploaded_file)
    elif ext == 'pdf':
        return parse_pdf(uploaded_file)
    else:
        raise FileParseError(f'Unsupported file type: .{ext}. Use CSV, XLSX, or PDF.')
