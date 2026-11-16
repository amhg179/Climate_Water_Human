"""HTML and Excel audit report (section 15: "إخراج تقرير HTML وExcel")."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, PackageLoader, select_autoescape

from . import __version__, config


def _img(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _table(df: pd.DataFrame, max_rows: int | None = None) -> str:
    view = df if max_rows is None else df.head(max_rows)
    return view.to_html(index=False, classes="tbl", border=0, na_rep="", float_format=lambda x: f"{x:,.4g}")


def write_excel(sheets: dict[str, pd.DataFrame], out: Path) -> Path:
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        book = writer.book
        header = book.add_format({"bold": True, "bg_color": "#1f4e79", "font_color": "white", "border": 1,
                                  "text_wrap": True, "valign": "top"})
        for name, df in sheets.items():
            sheet_name = name[:31]
            frame = df.copy()
            for col in frame.columns:
                if pd.api.types.is_datetime64_any_dtype(frame[col]):
                    frame[col] = frame[col].dt.date
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
            ws = writer.sheets[sheet_name]
            for i, col in enumerate(frame.columns):
                ws.write(0, i, str(col), header)
                width = max(len(str(col)), *(len(str(v)) for v in frame[col].head(200))) if len(frame) else len(
                    str(col))
                ws.set_column(i, i, min(max(width + 2, 10), 60))
            ws.freeze_panes(1, 0)
            if len(frame):
                ws.autofilter(0, 0, len(frame), len(frame.columns) - 1)
    return out


def write_html(context: dict, figures: dict[str, Path], out: Path) -> Path:
    env = Environment(loader=PackageLoader("climate_water_human", "templates"),
                      autoescape=select_autoescape(["html"]))
    tmpl = env.get_template("audit_report.html.j2")
    html = tmpl.render(
        **context,
        figures={k: _img(v) for k, v in figures.items()},
        table=_table,
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        version=__version__,
        doi=config.ZENODO_DOI,
        cfg=config,
    )
    out.write_text(html, encoding="utf-8")
    return out
