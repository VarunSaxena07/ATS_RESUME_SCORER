import contextlib
import importlib
import io
import logging
import re
import textwrap
from html.parser import HTMLParser

WEASYPRINT_INSTALLED = False
_WEASYPRINT_IMPORT_ERROR: Exception | None = None
_WEASYPRINT_HTML = None
_FALLBACK_WARNING_LOGGED = False

logger = logging.getLogger('ats_resume_scorer')

def generate_combined_pdf(html_docs: dict[str, str]) -> bytes:
    html_class = _get_weasyprint_html()
    if html_class is None:
        _log_fallback_once()
        return _generate_plain_text_pdf(html_docs)

    documents = []
    
    # Render all 3 HTML strings to WeasyPrint Document objects
    for name, html_str in html_docs.items():
        doc = html_class(string=html_str).render()
        documents.append(doc)
    
    # Merge them into the first document
    first_doc = documents[0]
    for other_doc in documents[1:]:
        for page in other_doc.pages:
            first_doc.pages.append(page)
            
    # Write combined PDF bytes
    pdf_bytes = first_doc.write_pdf()
    return pdf_bytes


def _get_weasyprint_html():
    global WEASYPRINT_INSTALLED, _WEASYPRINT_IMPORT_ERROR, _WEASYPRINT_HTML

    if _WEASYPRINT_HTML is not None:
        return _WEASYPRINT_HTML
    if _WEASYPRINT_IMPORT_ERROR is not None:
        return None

    try:
        # WeasyPrint prints native-library guidance during import when
        # GTK/Pango DLLs are missing on Windows. Capture it and use our fallback.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            module = importlib.import_module('weasyprint')
        _WEASYPRINT_HTML = module.HTML
        WEASYPRINT_INSTALLED = True
        return _WEASYPRINT_HTML
    except Exception as exc:
        _WEASYPRINT_IMPORT_ERROR = exc
        WEASYPRINT_INSTALLED = False
        return None


def _log_fallback_once() -> None:
    global _FALLBACK_WARNING_LOGGED
    if _FALLBACK_WARNING_LOGGED:
        return
    reason = str(_WEASYPRINT_IMPORT_ERROR or 'not installed').split('  Additionally', 1)[0]
    logger.warning(
        'WeasyPrint unavailable; using plain-text PDF fallback. '
        f'Install GTK/Pango native libraries for styled reports. Reason: {reason}'
    )
    _FALLBACK_WARNING_LOGGED = True


class _HTMLTextExtractor(HTMLParser):
    _BLOCK_TAGS = {
        'address', 'article', 'aside', 'blockquote', 'br', 'div', 'footer',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'li', 'main', 'p',
        'section', 'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr',
        'ul', 'ol',
    }

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {'style', 'script'}:
            self._skip_depth += 1
            return
        if tag == 'li':
            self._parts.append('\n- ')
        elif tag in self._BLOCK_TAGS:
            self._parts.append('\n')

    def handle_endtag(self, tag: str) -> None:
        if tag in {'style', 'script'} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag in self._BLOCK_TAGS:
            self._parts.append('\n')

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = re.sub(r'\s+', ' ', data).strip()
        if text:
            self._parts.append(text + ' ')

    def text(self) -> str:
        text = ''.join(self._parts)
        text = re.sub(r'[ \t]+\n', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


def _html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.text()


def _generate_plain_text_pdf(html_docs: dict[str, str]) -> bytes:
    lines: list[str] = []
    for report_name, html in html_docs.items():
        title = report_name.replace('_', ' ').title()
        lines.extend([title, '=' * len(title)])
        lines.extend(_wrap_pdf_text(_html_to_text(html)))
        lines.append('')

    return _write_text_pdf(lines)


def _wrap_pdf_text(text: str) -> list[str]:
    wrapped: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            wrapped.append('')
            continue
        wrapped.extend(textwrap.wrap(line, width=92) or [''])
    return wrapped


def _write_text_pdf(lines: list[str]) -> bytes:
    page_width = 612
    page_height = 792
    margin_x = 48
    top_y = 744
    bottom_y = 48
    font_size = 10
    line_height = 14
    lines_per_page = max(1, int((top_y - bottom_y) / line_height))

    pages = [
        lines[i:i + lines_per_page]
        for i in range(0, len(lines), lines_per_page)
    ] or [[]]

    objects: list[bytes] = []
    page_object_ids: list[int] = []
    content_object_ids: list[int] = []

    catalog_id = 1
    pages_id = 2
    font_id = 3
    next_id = 4

    for page_lines in pages:
        page_object_ids.append(next_id)
        next_id += 1
        content_object_ids.append(next_id)
        next_id += 1

    def add_object(object_id: int, body: bytes) -> None:
        objects.append(f'{object_id} 0 obj\n'.encode('ascii') + body + b'\nendobj\n')

    add_object(catalog_id, b'<< /Type /Catalog /Pages 2 0 R >>')
    kids = b' '.join(f'{page_id} 0 R'.encode('ascii') for page_id in page_object_ids)
    add_object(pages_id, b'<< /Type /Pages /Kids [' + kids + b'] /Count ' + str(len(pages)).encode('ascii') + b' >>')
    add_object(font_id, b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')

    for page_id, content_id, page_lines in zip(page_object_ids, content_object_ids, pages):
        page_body = (
            b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 '
            + str(page_width).encode('ascii')
            + b' '
            + str(page_height).encode('ascii')
            + b'] /Resources << /Font << /F1 3 0 R >> >> /Contents '
            + f'{content_id} 0 R'.encode('ascii')
            + b' >>'
        )
        add_object(page_id, page_body)

        stream = _pdf_text_stream(page_lines, margin_x, top_y, font_size, line_height)
        content_body = (
            b'<< /Length ' + str(len(stream)).encode('ascii') + b' >>\nstream\n'
            + stream
            + b'\nendstream'
        )
        add_object(content_id, content_body)

    buffer = io.BytesIO()
    buffer.write(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = [0]
    for obj in sorted(objects, key=lambda item: int(item.split(b' ', 1)[0])):
        offsets.append(buffer.tell())
        buffer.write(obj)

    xref_offset = buffer.tell()
    buffer.write(f'xref\n0 {len(offsets)}\n'.encode('ascii'))
    buffer.write(b'0000000000 65535 f \n')
    for offset in offsets[1:]:
        buffer.write(f'{offset:010d} 00000 n \n'.encode('ascii'))
    buffer.write(
        b'trailer\n<< /Size '
        + str(len(offsets)).encode('ascii')
        + b' /Root 1 0 R >>\nstartxref\n'
        + str(xref_offset).encode('ascii')
        + b'\n%%EOF\n'
    )
    return buffer.getvalue()


def _pdf_text_stream(
    lines: list[str],
    x: int,
    y: int,
    font_size: int,
    line_height: int,
) -> bytes:
    commands = [f'BT /F1 {font_size} Tf {line_height} TL {x} {y} Td'.encode('ascii')]
    for index, line in enumerate(lines):
        if index:
            commands.append(b'T*')
        commands.append(b'(' + _escape_pdf_text(line) + b') Tj')
    commands.append(b'ET')
    return b'\n'.join(commands)


def _escape_pdf_text(text: str) -> bytes:
    value = text.encode('latin-1', errors='replace')
    value = value.replace(b'\\', b'\\\\')
    value = value.replace(b'(', b'\\(')
    value = value.replace(b')', b'\\)')
    return value
