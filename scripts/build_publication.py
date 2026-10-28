"""Build the shareable report from preserved facts. Requires matplotlib, reportlab and pandoc.

Run with the publication/build Python, not the project's pinned experiment venv.
No dependencies or scientific artifacts are modified; no model calls are made.
"""

import base64
import json
import os
import re
import subprocess

os.environ.setdefault("MPLCONFIGDIR", "/tmp/fragmentguard-final/matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from publication_facts import ROOT, facts

OUT = ROOT / "publication"


def figures(data):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "svg.hashsalt": "fragmentguard-final"})
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.5))
    for ax, group, title in zip(
        axes, ["complete", "masked"], ["Complete publications", "Masked observations"], strict=True
    ):
        values = data["raw_evidence_support_by_budget"]["3"][group]
        n = values["correlated"]["observations"]
        counts = [values["correlated"]["sufficient_support"], values["streaming_provenance"]["sufficient_support"]]
        ax.barh([1, 0], counts, color=["#176b80", "#cb7c34"], height=0.5)
        ax.set_yticks([1, 0], ["Original\ncorrelation", "Streaming +\nprovenance"])
        ax.set_xlim(0, n * 1.13)
        for y, count in zip([1, 0], counts, strict=True):
            ax.text(count + n * 0.025, y, f"{count}/{n}", va="center", fontsize=11, fontweight="bold")
        ax.set_title(title, loc="left", fontsize=12, fontweight="bold", pad=16)
        ax.set_xlabel("Publications with sufficient raw evidence", fontsize=9)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.spines["bottom"].set_color("#b7c6cf")
        ax.tick_params(axis="y", length=0)
        ax.set_axisbelow(True)
        ax.grid(axis="x", color="#e5ebee", linewidth=0.7)
    fig.suptitle("Supporting evidence within a three-record checker budget", fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout(w_pad=2)
    fig.savefig(OUT / "figures/support.svg", bbox_inches="tight", metadata={"Date": None})
    fig.savefig(OUT / "figures/support.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 2.3))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 2)
    ax.axis("off")
    boxes = [
        (0.05, "Restricted root", "Trusted catalog", "#f8e8d5"),
        (2.65, "Collector", "read → draft", "#e5f1f4"),
        (5.25, "Processor", "transform → summary", "#e5f1f4"),
        (7.85, "Publisher", "publish → public", "#f8e8d5"),
    ]
    for x, title, detail, color in boxes:
        ax.add_patch(
            FancyBboxPatch(
                (x, 0.75), 2.05, 0.9, boxstyle="round,pad=.04", facecolor=color, edgecolor="#9db3bf", linewidth=1
            )
        )
        ax.text(x + 1.025, 1.30, title, ha="center", fontsize=11, fontweight="bold", color="#142b3b")
        ax.text(x + 1.025, 0.98, detail, ha="center", fontsize=9, color="#526473")
    for start, end in [(2.12, 2.60), (4.72, 5.20), (7.32, 7.80)]:
        ax.annotate(
            "", xy=(end, 1.2), xytext=(start, 1.2), arrowprops={"arrowstyle": "->", "color": "#176b80", "lw": 1.7}
        )
    ax.text(5, 0.23, "The relevant dependency crosses agent boundaries.", ha="center", fontsize=11, color="#176b80")
    fig.savefig(OUT / "figures/workflow.svg", bbox_inches="tight", metadata={"Date": None})
    fig.savefig(OUT / "figures/workflow.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def main():
    data = facts()
    (OUT / "results.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    figures(data)
    body = subprocess.check_output(
        ["pandoc", str(ROOT / "docs/final_report.md"), "-f", "gfm-tex_math_dollars", "-t", "html5"], text=True
    )

    def inline(match):
        path = (ROOT / "docs" / match.group(1)).resolve()
        if not path.is_relative_to(OUT):
            raise ValueError("Unexpected report image path")
        return 'src="data:image/svg+xml;base64,' + base64.b64encode(path.read_bytes()).decode() + '"'

    body = re.sub(r'src="([^"]+\.svg)"', inline, body)
    template = (OUT / "template.html").read_text()
    html = template.replace("__PUBLICATION_CSS__", (OUT / "style.css").read_text()).replace("$body$", body)
    (OUT / "index.html").write_text(html)
    from publication_pdf import build_pdf

    build_pdf(OUT / "FragmentGuard-final-report.pdf")
    print(OUT / "FragmentGuard-final-report.pdf")


if __name__ == "__main__":
    main()
