"""
PDF exporter — converts markdown reports to PDF using fpdf2.
Pure Python, no external API keys. Works on Linux (Docker), Windows, macOS.

Font requirements (Cyrillic support):
  Linux/Docker: apt-get install -y fonts-dejavu-core
  Windows:      Arial is used automatically (built-in)
"""
import re
from pathlib import Path
from typing import Optional, Tuple


def _find_fonts() -> Tuple[Optional[str], Optional[str]]:
    """
    Return (regular_font_path, bold_font_path) for a Unicode-capable TTF font.
    Bold may be None — headers will use size difference instead.
    """
    candidates = [
        # Linux / Docker (fonts-dejavu-core)
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
        # Liberation (common on RHEL/CentOS/Ubuntu)
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ("/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/liberation/LiberationSans-Bold.ttf"),
        # Noto
        ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
         "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
        # Windows
        ("C:/Windows/Fonts/arial.ttf",
         "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/calibri.ttf",
         "C:/Windows/Fonts/calibrib.ttf"),
        # macOS
        ("/Library/Fonts/Arial.ttf",
         "/Library/Fonts/Arial Bold.ttf"),
        ("/System/Library/Fonts/Supplemental/Arial.ttf",
         "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ]
    for regular, bold in candidates:
        if Path(regular).exists():
            bold_path = bold if Path(bold).exists() else None
            return regular, bold_path
    return None, None


def _strip_md(text: str) -> str:
    """Strip inline markdown for clean PDF text."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    return text


def export_md_to_pdf(md_path: Path) -> Path:
    """
    Convert a markdown file to PDF.
    Returns path to the created PDF (same dir, .pdf extension).
    Raises RuntimeError if fpdf2 is missing or no Unicode font found.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        raise RuntimeError("fpdf2 not installed. Run: pip install fpdf2")

    font_regular, font_bold = _find_fonts()
    if not font_regular:
        raise RuntimeError(
            "No Unicode font found on this system.\n"
            "  Linux/Docker: apt-get install -y fonts-dejavu-core\n"
            "  Windows: Arial should be available at C:/Windows/Fonts/arial.ttf\n"
        )

    md_text = md_path.read_text(encoding="utf-8")
    lines = md_text.splitlines()

    pdf = FPDF()
    pdf.set_margins(20, 15, 20)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.add_font("Regular", "", font_regular)
    if font_bold:
        pdf.add_font("Bold", "", font_bold)
    # If no separate bold font, bold headings use Regular at larger size

    def _set_normal():
        pdf.set_font("Regular", size=10)
        pdf.set_text_color(30, 30, 30)

    def _set_h1():
        pdf.set_font("Bold" if font_bold else "Regular", size=16)
        pdf.set_text_color(10, 10, 10)

    def _set_h2():
        pdf.set_font("Bold" if font_bold else "Regular", size=13)
        pdf.set_text_color(10, 10, 10)

    def _set_h3():
        pdf.set_font("Bold" if font_bold else "Regular", size=11)
        pdf.set_text_color(40, 40, 40)

    _set_normal()

    def _reset_x():
        pdf.set_x(pdf.l_margin)

    for line in lines:
        raw = line.rstrip()

        # H1
        if re.match(r'^# [^#]', raw):
            text = _strip_md(raw[2:].strip())
            pdf.ln(4)
            _reset_x()
            _set_h1()
            pdf.multi_cell(0, 8, text)
            _set_normal()
            pdf.ln(2)

        # H2
        elif re.match(r'^## [^#]', raw):
            text = _strip_md(raw[3:].strip())
            pdf.ln(3)
            _reset_x()
            _set_h2()
            pdf.multi_cell(0, 7, text)
            _set_normal()
            pdf.ln(1)

        # H3+
        elif re.match(r'^#{3,}\s', raw):
            text = _strip_md(re.sub(r'^#+\s+', '', raw))
            pdf.ln(2)
            _reset_x()
            _set_h3()
            pdf.multi_cell(0, 6, text)
            _set_normal()

        # Horizontal rule
        elif re.match(r'^-{3,}$', raw):
            pdf.ln(2)
            _reset_x()
            pdf.set_draw_color(180, 180, 180)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)

        # Bullet: - item or • item
        elif re.match(r'^[-•]\s', raw):
            text = _strip_md(raw[2:].strip())
            _reset_x()
            pdf.multi_cell(0, 5, f"    \u2022 {text}")

        # Empty line
        elif not raw:
            pdf.ln(3)

        # Normal paragraph text
        else:
            text = _strip_md(raw)
            if text:
                _reset_x()
                pdf.multi_cell(0, 5, text)

    out_path = md_path.with_suffix(".pdf")
    pdf.output(str(out_path))
    return out_path
