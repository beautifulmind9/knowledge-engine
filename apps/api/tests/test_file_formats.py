import io
from ebooklib import epub
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from app.services.text_extraction import extract_text_from_file


def test_pdf_text_extraction(tmp_path):
    writer=PdfWriter()
    page=writer.add_blank_page(width=612,height=792)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 40 700 Td (Test assumptions before committing resources.) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(stream)
    path=tmp_path/'notes.pdf'
    with path.open('wb') as handle:writer.write(handle)
    assert 'Test assumptions before committing resources.' in extract_text_from_file(str(path),'.pdf')


def test_epub_extraction(tmp_path):
    book=epub.EpubBook();book.set_identifier('synthetic-demo');book.set_title('Testing ideas');book.set_language('en')
    chapter=epub.EpubHtml(title='Experiment',file_name='chapter.xhtml',lang='en')
    chapter.content='<h1>Experiment</h1><p>Use a small test to reduce uncertainty.</p>'
    book.add_item(chapter);book.spine=[chapter]
    book.toc=(epub.Link("chapter.xhtml", "Experiment", "chapter"),)
    book.add_item(epub.EpubNcx());book.add_item(epub.EpubNav())
    path=tmp_path/'notes.epub';epub.write_epub(str(path),book)
    assert 'Use a small test to reduce uncertainty.' in extract_text_from_file(str(path),'.epub')
