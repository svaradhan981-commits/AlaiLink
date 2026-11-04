from app.services.documents import chunk_text, extract_document, load_documents


def test_extract_text_page_preserves_title_url_and_text(tmp_path):
    page = tmp_path / "scheme.txt"
    page.write_text(
        "TITLE: Official Relief Scheme\n"
        "SOURCE_URL: https://www.fisheries.tn.gov.in/schemes/relief\n\n"
        "Eligibility information is published here.\n",
        encoding="utf-8",
    )

    document = extract_document(page)

    assert document.title == "Official Relief Scheme"
    assert document.source_url == "https://www.fisheries.tn.gov.in/schemes/relief"
    assert "Eligibility information" in document.text


def test_extract_html_title_canonical_url_and_visible_text(tmp_path):
    page = tmp_path / "scheme.html"
    page.write_text(
        "<html><head><title>Official Scheme</title>"
        '<link rel="canonical" href="https://example.gov/scheme"></head>'
        "<body><nav>Navigation</nav><main><p>Visible scheme text.</p>"
        "<script>ignored()</script></main></body></html>",
        encoding="utf-8",
    )

    document = extract_document(page)

    assert document.title == "Official Scheme"
    assert document.source_url == "https://example.gov/scheme"
    assert "Visible scheme text." in document.text
    assert "Navigation" not in document.text
    assert "ignored()" not in document.text


def test_chunking_keeps_chunks_within_limit_and_overlaps():
    text = "Sentence one. " + "Sentence two " * 22 + ". Sentence three."

    chunks = chunk_text(text, max_chars=90, overlap_chars=20)

    assert len(chunks) > 1
    assert all(len(chunk) <= 90 for chunk in chunks)
    assert all(chunks[index].split()[-1] in chunks[index + 1] for index in range(1, len(chunks) - 2))


def test_chunking_handles_words_longer_than_chunk_size():
    chunks = chunk_text("x" * 230, max_chars=90, overlap_chars=20)

    assert [len(chunk) for chunk in chunks] == [90, 90, 50]


def test_load_documents_skips_duplicate_text_sources(tmp_path):
    pages = tmp_path / "pages"
    pdfs = tmp_path / "pdfs"
    pages.mkdir()
    pdfs.mkdir()
    page_text = (
        "TITLE: Official Page\n"
        "SOURCE_URL: https://www.fisheries.tn.gov.in/example\n\n"
        "Same official scheme content."
    )
    (pages / "first.txt").write_text(page_text, encoding="utf-8")
    (pages / "duplicate.txt").write_text(page_text, encoding="utf-8")

    documents = list(load_documents(pages, pdfs))

    assert len(documents) == 1
