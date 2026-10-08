"""Write assets/templates/template.xlsx (the effort workbook skeleton) from policy/workbook.yaml.

Run after changing workbook.yaml headers/titles. Presales may then restyle the saved template in Excel
(fonts, fills, widths) - the filler keeps those styles - as long as each table sheet keeps its shape:
title row 1, header row 3, prototype data row 4, prototype total row 5, and the '_lob' prototype sheet.

    python scripts/build_templates.py
"""

from __future__ import annotations

from bidcore.paths import templates_dir
from bidcore.policy import get_policy
from bidcore.render.workbook.filler import TEMPLATE_NAME
from bidcore.render.workbook.template_builder import build_template


def main() -> None:
    out = templates_dir()
    out.mkdir(parents=True, exist_ok=True)
    build_template(get_policy()).save(out / TEMPLATE_NAME)
    print(f"wrote {out / TEMPLATE_NAME}")


if __name__ == "__main__":
    main()
