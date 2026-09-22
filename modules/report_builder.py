"""
report_builder.py - Turns a ResultsCollector (one deployment run's worth
of per-item outcomes) into the shared HTML report from html_report.py.

Kept deliberately thin: results.py owns what a "result" is, html_report.py
owns how a report looks, this just maps one onto the other.
"""

import os
from modules.html_report import render_operation_html_report, ReportRow
from modules.results import ResultsCollector, STATUS_SUCCESS, STATUS_FAILED, STATUS_SKIPPED


def build_deployment_report(collector: ResultsCollector, output_path: str,
                             json_log_path: str = None,
                             title: str = "Deployment Report",
                             subtitle: str = "") -> str:
    """Renders collector's items to a self-contained HTML file at
    output_path and returns that path. Callers should already have
    called collector.mark_finished() if they want an accurate 'finished'
    timestamp reflected in the subtitle."""
    counts = collector.counts()
    total = len(collector.items)

    summary_cards = [
        ("Total", total, "neutral"),
        ("Succeeded", counts.get(STATUS_SUCCESS, 0), "good"),
        ("Failed", counts.get(STATUS_FAILED, 0), "bad"),
        ("Skipped", counts.get(STATUS_SKIPPED, 0), "warn"),
    ]

    rows = []
    for item in collector.items:
        label, css_class = item.badge()
        rows.append(ReportRow(
            name=f"{item.name} ({item.category})" if item.category else item.name,
            source=item.source,
            dest=item.dest,
            status_label=label,
            status_class=css_class,
            detail=item.message,
        ))

    if not subtitle:
        started = collector.started_at or ""
        finished = collector.finished_at or ""
        subtitle = f"Started {started}" + (f" &middot; finished {finished}" if finished else "")

    html_text = render_operation_html_report(
        title=title,
        subtitle=subtitle,
        summary_cards=summary_cards,
        rows=rows,
        json_log_path=json_log_path,
    )

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_text)
    return output_path
