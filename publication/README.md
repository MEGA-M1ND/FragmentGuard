# Final publication files

This is the completed project presentation, not an additional experiment.

- `../docs/final_report.md`: editable canonical write-up.
- `FragmentGuard-final-report.pdf`: shareable report.
- `index.html`: self-contained HTML report with inline figures and styles.
- `submission.md`: ready-to-paste submission summary.
- `results.json`: facts extracted from committed evidence by `../scripts/publication_facts.py`.
- `figures/`: standalone SVG and PNG figures.
- `project_status.json`: closed scope; the proposed four-case live successor is unrun.
- `validation.json`: final checks and preserved-evidence verification.

Rebuild the presentation using a Python with matplotlib and ReportLab, plus `pandoc` installed:

```bash
python3 scripts/build_publication.py
```

The publication tooling uses the existing result files; it never calls a model.
It is separate from the experiment's pinned Python environment and does not change
scientific dependencies, scenarios, source logic or lockfiles. The HTML is fully
self-contained for offline viewing. The PDF has clickable source links. Generated
PDF metadata can differ across builds; the published asset checksums identify the
release files, while the scientific artifact hashes remain authoritative for data.

The evidence base is commit `aed2a1c969267e1f70dfeac8255daa9f4443ed13`.
Historical source/data manifests are unchanged. The `final-project-report-2026-10-28` tag is a
publication snapshot, not a claim that this experimental software is production-ready.

The report bundle is `FragmentGuard-report-bundle.zip`. From the repository root,
verify its download and the report files with `sha256sum -c publication/SHA256SUMS`.
Release downloads use versioned repository files, with no separate hosting dependency.
