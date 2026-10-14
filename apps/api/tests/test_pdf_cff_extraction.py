"""PDF text extraction coverage for embedded CFF Type1 fonts."""
from io import BytesIO

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

from app.services.text_extraction import extract_text_from_file


def _font_data():
    """Build a tiny CFF OpenType font in memory for an embedded-PDF fixture."""
    glyphs = [".notdef", "space", "A", "B", "C"]
    builder = FontBuilder(1000, isTTF=False)
    builder.setupGlyphOrder(glyphs)
    builder.setupCharacterMap({32: "space", 65: "A", 66: "B", 67: "C"})

    def char_string(name):
        pen = T2CharStringPen(600, None)
        if name != "space":
            pen.moveTo((50, 0))
            pen.lineTo((550, 0))
            pen.lineTo((550, 700))
            pen.lineTo((50, 700))
            pen.closePath()
        return pen.getCharString()

    builder.setupCFF(
        "SyntheticCFF-Regular",
        {"FullName": "Synthetic CFF Regular", "FamilyName": "Synthetic CFF", "Weight": "Regular"},
        {name: char_string(name) for name in glyphs},
        {},
    )
    builder.setupHorizontalMetrics({name: (600, 0) for name in glyphs})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({
        "familyName": "Synthetic CFF", "styleName": "Regular",
        "uniqueFontIdentifier": "SyntheticCFF", "fullName": "Synthetic CFF Regular",
        "psName": "SyntheticCFF-Regular",
    })
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    builder.setupMaxp()
    otf = BytesIO()
    builder.font.save(otf)
    return TTFont(BytesIO(otf.getvalue())).getTableData("CFF ")


def _write_pdf(path, *, embedded_cff, text):
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=100)

    descriptor_ref = None
    if embedded_cff:
        font_file = DecodedStreamObject()
        font_file.set_data(_font_data())
        font_file[NameObject("/Subtype")] = NameObject("/Type1C")
        font_file_ref = writer._add_object(font_file)
        descriptor = DictionaryObject({
            NameObject("/Type"): NameObject("/FontDescriptor"),
            NameObject("/FontName"): NameObject("/SyntheticCFF-Regular"),
            NameObject("/Flags"): NumberObject(32),
            NameObject("/FontBBox"): ArrayObject([NumberObject(n) for n in (0, -200, 600, 800)]),
            NameObject("/ItalicAngle"): NumberObject(0),
            NameObject("/Ascent"): NumberObject(800),
            NameObject("/Descent"): NumberObject(-200),
            NameObject("/CapHeight"): NumberObject(700),
            NameObject("/StemV"): NumberObject(80),
            NameObject("/FontFile3"): font_file_ref,
        })
        descriptor_ref = writer._add_object(descriptor)

    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/SyntheticCFF-Regular" if embedded_cff else "/Helvetica"),
        NameObject("/FirstChar"): NumberObject(32),
        NameObject("/LastChar"): NumberObject(122),
        NameObject("/Widths"): ArrayObject([NumberObject(600) for _ in range(91)]),
        NameObject("/Encoding"): NameObject("/StandardEncoding" if embedded_cff else "/WinAnsiEncoding"),
    })
    if descriptor_ref:
        font[NameObject("/FontDescriptor")] = descriptor_ref
    font_ref = writer._add_object(font)
    resources = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref}),
    })
    page[NameObject("/Resources")] = writer._add_object(resources)
    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 20 50 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)
    with path.open("wb") as output:
        writer.write(output)


def test_embedded_cff_type1_pdf_extracts_usable_text_deterministically(tmp_path):
    pdf = tmp_path / "embedded-cff.pdf"
    _write_pdf(pdf, embedded_cff=True, text="ABC")

    first = extract_text_from_file(str(pdf), ".pdf")
    second = extract_text_from_file(str(pdf), ".pdf")

    assert first == "ABC"
    assert second == first


def test_ordinary_pdf_text_extraction_is_unchanged(tmp_path):
    pdf = tmp_path / "ordinary.pdf"
    _write_pdf(pdf, embedded_cff=False, text="Normal PDF text")

    assert extract_text_from_file(str(pdf), ".pdf") == "Normal PDF text"
