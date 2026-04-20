"""Standalone script that creates the sample_pattern_native_roadmap.xlsx fixture.

Run directly:
    python tests/fixtures/build_fixture.py

Or import and call build() from a pytest conftest.
"""
from __future__ import annotations

import os
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

FIXTURE_DIR = Path(__file__).parent
FIXTURE_PATH = FIXTURE_DIR / "sample_pattern_native_roadmap.xlsx"


def build(output_path: str | Path | None = None) -> Path:
    """Create the fixture xlsx. Returns the path written to."""
    out = Path(output_path) if output_path else FIXTURE_PATH
    wb = openpyxl.Workbook()

    # ── Remove default sheet ───────────────────────────────────────────────────
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    # ── 1. Breakdown sheet ─────────────────────────────────────────────────────
    # Col E (index 4, col 5) has focus labels; cols G:R (cols 7-18) have monthly hours
    ws_bd = wb.create_sheet("Breakdown")

    # Add some header content in other columns to make it realistic
    ws_bd.cell(row=1, column=1, value="SEO Retainer Breakdown")
    ws_bd.cell(row=2, column=1, value="Client:")
    ws_bd.cell(row=2, column=2, value="Sample Retail Co")

    # Row 4: Consulting Hours — 12 monthly values in G:R
    ws_bd.cell(row=4, column=1, value="Service")
    ws_bd.cell(row=4, column=5, value="Consulting Hours")
    consulting_hours = [8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8]
    for i, h in enumerate(consulting_hours):
        ws_bd.cell(row=4, column=7 + i, value=h)

    # Row 6: Technical Hours
    ws_bd.cell(row=6, column=5, value="Technical Hours")
    technical_hours = [12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12]
    for i, h in enumerate(technical_hours):
        ws_bd.cell(row=6, column=7 + i, value=h)

    # Row 8: Content Hours
    ws_bd.cell(row=8, column=5, value="Content Hours")
    content_hours = [20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20]
    for i, h in enumerate(content_hours):
        ws_bd.cell(row=8, column=7 + i, value=h)

    # Row 10: Link Hours
    ws_bd.cell(row=10, column=5, value="Link Hours")
    link_hours = [6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6]
    for i, h in enumerate(link_hours):
        ws_bd.cell(row=10, column=7 + i, value=h)

    # ── 2. Client Detail sheet ─────────────────────────────────────────────────
    ws_cd = wb.create_sheet("1. Client Detail")

    ws_cd.cell(row=1, column=1, value="SEO Retainer Agreement")
    ws_cd.cell(row=2, column=1, value="---")

    client_data = [
        (3, "Client Name", "Sample Retail Co"),
        (4, "Industry", "Fashion"),
        (5, "Monthly Retainer", "AUD 5000"),
        (6, "Project Start Date", "2026-07-01"),
        (7, "CMS", "Shopify"),
        (8, "Primary Contact", "Jane Smith"),
        (9, "Account Manager", "John Doe"),
        (10, "Contract Period", "12 months"),
    ]
    for row, label, value in client_data:
        ws_cd.cell(row=row, column=1, value=label)
        ws_cd.cell(row=row, column=2, value=value)

    # ── 3. Consulting sheet ────────────────────────────────────────────────────
    ws_con = wb.create_sheet("2. Consulting")

    consulting_headers = ["Task", "Focus", "Occurrence", "Hours"]
    for col, h in enumerate(consulting_headers, 1):
        ws_con.cell(row=1, column=col, value=h)

    consulting_tasks = [
        ("Monthly Strategy Review", "Strategy", "Monthly", 4),
        ("Keyword Research & Mapping", "Strategy", "Quarterly", 8),
        ("Competitor Analysis", "Strategy", "Quarterly", 6),
        ("GA4 & GSC Reporting", "Analytics", "Monthly", 3),
        ("Content Gap Analysis", "Strategy", "Bi-Annual", 8),
    ]
    for row_idx, (task, focus, occ, hrs) in enumerate(consulting_tasks, 2):
        ws_con.cell(row=row_idx, column=1, value=task)
        ws_con.cell(row=row_idx, column=2, value=focus)
        ws_con.cell(row=row_idx, column=3, value=occ)
        ws_con.cell(row=row_idx, column=4, value=hrs)

    # ── 4. Technical sheet ─────────────────────────────────────────────────────
    ws_tech = wb.create_sheet("3. Technical")

    tech_headers = ["Task", "Focus", "Occurrence", "Hours"]
    for col, h in enumerate(tech_headers, 1):
        ws_tech.cell(row=1, column=col, value=h)

    technical_tasks = [
        ("Core Web Vitals Audit", "Technical", "Quarterly", 6),
        ("Crawl Error Remediation", "Technical", "Monthly", 4),
        ("Schema Markup Implementation", "Technical", "Quarterly", 8),
        ("Site Speed Optimisation", "Technical", "Monthly", 4),
        ("Internal Linking Audit", "Technical", "Bi-Annual", 10),
    ]
    for row_idx, (task, focus, occ, hrs) in enumerate(technical_tasks, 2):
        ws_tech.cell(row=row_idx, column=1, value=task)
        ws_tech.cell(row=row_idx, column=2, value=focus)
        ws_tech.cell(row=row_idx, column=3, value=occ)
        ws_tech.cell(row=row_idx, column=4, value=hrs)

    # ── 5. Content sheet ───────────────────────────────────────────────────────
    # Header at row 7, data rows 8+
    # Columns: A=Month#, B=Month Name, C=URL, D=Title, E=Focus, F=Priority, G=Content Type, H=Word Count, I=SEO Hours
    ws_cont = wb.create_sheet("4. Content")

    ws_cont.cell(row=1, column=1, value="Content Production Plan")
    ws_cont.cell(row=2, column=1, value="12-Month Schedule")

    # Header row at row 7
    content_headers = ["Month", "Month Name", "URL", "Title", "Focus", "Priority", "Content Type", "Word Count", "SEO Hours"]
    for col, h in enumerate(content_headers, 1):
        ws_cont.cell(row=7, column=col, value=h)

    content_rows = [
        (1, "July",      "/blog/summer-fashion-guide",         "Summer Fashion Guide 2026",    "Content", "High", "New Page - Long Form",          2000, 3),
        (1, "July",      "/faq/how-to-style-denim",            "How to Style Denim - FAQ",     "Content", "Medium", "FAQ Page",                    800,  2),
        (2, "August",    "/blog/spring-trends",                "Spring Trends 2026",           "Content", "High", "New Page - Long Form",          1800, 3),
        (2, "August",    "/categories/womens-dresses",         "Women's Dresses Category",     "Content", "High", "Optimisation",                  500,  2),
        (3, "September", "/blog/workwear-essentials",          "Workwear Essentials Guide",    "Content", "Medium", "New Page - Long Form",        2200, 4),
        (3, "September", "/products/classic-blazer",          "Classic Blazer Product Page",   "Content", "Low", "Optimisation",                  400,  1),
        (4, "October",   "/blog/autumn-layering",             "Autumn Layering Techniques",    "Content", "High", "New Page - Long Form",         1900, 3),
    ]
    for row_idx, row_data in enumerate(content_rows, 8):
        for col_idx, val in enumerate(row_data, 1):
            ws_cont.cell(row=row_idx, column=col_idx, value=val)

    # ── 6. Links sheet ────────────────────────────────────────────────────────
    ws_links = wb.create_sheet("5. Links")

    links_headers = ["Task", "Focus", "Occurrence", "Hours"]
    for col, h in enumerate(links_headers, 1):
        ws_links.cell(row=1, column=col, value=h)

    links_tasks = [
        ("Digital PR Outreach", "Off-Page", "Monthly", 4),
        ("Guest Post Sourcing", "Off-Page", "Monthly", 2),
        ("Link Reclamation", "Off-Page", "Quarterly", 3),
    ]
    for row_idx, (task, focus, occ, hrs) in enumerate(links_tasks, 2):
        ws_links.cell(row=row_idx, column=1, value=task)
        ws_links.cell(row=row_idx, column=2, value=focus)
        ws_links.cell(row=row_idx, column=3, value=occ)
        ws_links.cell(row=row_idx, column=4, value=hrs)

    wb.save(out)
    return out


if __name__ == "__main__":
    path = build()
    print(f"Fixture written to: {path}")
