# Detailed research report

This is a detailed exposition of FragmentGuard's completed experiments, dated 29 October 2026. It adds no experimental results and preserves the existing publication snapshots.

- [Editable Word document](FragmentGuard-detailed-report.docx): upload this file to Google Drive and open it in Google Docs.
- [PDF](FragmentGuard-detailed-report.pdf): fixed layout, searchable text, clickable contents and source links.
- [Markdown source](FragmentGuard-detailed-report.md): editable source of both documents.
- [Validation record](validation.json) and [checksums](SHA256SUMS).

The report contains approximately 7,700 words, 16 main sections, 12 tables, two embedded figures, a glossary, offline reproduction commands and linked evidence. The DOCX uses standard headings, editable tables and embedded images. Its layout may repaginate in Google Docs; the PDF preserves the inspected layout.

## Put the document in Google Drive

1. Download `FragmentGuard-detailed-report.docx`.
2. In Google Drive, choose **New → File upload** and select the file.
3. Open the uploaded file with **Google Docs**.
4. To create a native Google document, choose **File → Save as Google Docs** if the document remains in Word editing mode.
5. Use **Share** to choose the audience and access level you want.

## Rebuild

From the repository root, using a build Python with `python-docx` and `reportlab`, plus Pandoc and DejaVu fonts:

```bash
python3 publication/detailed-report/build_report.py
```

The renderer also uses the existing inline formatting helper in `scripts/publication_pdf.py` and the published PNG figures in `publication/figures/`. It does not change the experiment environment or run models. Regenerated container/PDF metadata can differ; checksums identify the exact shared files.

Verify the files from this directory with `sha256sum -c SHA256SUMS`. Google Drive upload and permission changes are performed by the document owner; this package does not claim that a Google document has already been created.
