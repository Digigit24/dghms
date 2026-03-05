#!/usr/bin/env python3
"""Generate professional PDF from TECHNICAL_DOCUMENTATION.md"""

import markdown
from weasyprint import HTML, CSS
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MD_FILE = os.path.join(SCRIPT_DIR, "TECHNICAL_DOCUMENTATION.md")
PDF_FILE = os.path.join(SCRIPT_DIR, "TECHNICAL_DOCUMENTATION.pdf")

# Read markdown
with open(MD_FILE, "r") as f:
    md_content = f.read()

# Convert markdown to HTML
html_body = markdown.markdown(
    md_content,
    extensions=[
        "tables",
        "toc",
        "fenced_code",
        "codehilite",
        "attr_list",
        "md_in_html",
    ],
    extension_configs={
        "toc": {"permalink": False, "toc_depth": 3},
        "codehilite": {"css_class": "highlight", "guess_lang": False},
    },
)

# Professional CSS
css = """
@page {
    size: A4;
    margin: 2cm 2.2cm 2.5cm 2.2cm;

    @top-right {
        content: "DigiHMS - Technical Documentation";
        font-size: 8pt;
        color: #888;
        font-family: 'Segoe UI', Arial, sans-serif;
    }
    @bottom-center {
        content: "Page " counter(page) " of " counter(pages);
        font-size: 8pt;
        color: #888;
        font-family: 'Segoe UI', Arial, sans-serif;
    }
    @bottom-right {
        content: "Confidential";
        font-size: 7pt;
        color: #bbb;
        font-family: 'Segoe UI', Arial, sans-serif;
    }
}

@page :first {
    @top-right { content: none; }
    @bottom-center { content: none; }
    @bottom-right { content: none; }
}

body {
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.6;
    color: #1a1a1a;
}

/* ===== TITLE PAGE ===== */
h1:first-of-type {
    page-break-before: avoid;
    font-size: 28pt;
    color: #0d47a1;
    border-bottom: 3px solid #0d47a1;
    padding-bottom: 12px;
    margin-top: 120px;
    margin-bottom: 6px;
    text-align: center;
    letter-spacing: 1px;
}

/* Subtitle (first h2 right after h1) */
h1:first-of-type + h2 {
    font-size: 16pt;
    color: #37474f;
    text-align: center;
    border: none;
    margin-top: 0;
    padding-top: 0;
    font-weight: 400;
}

h1:first-of-type + h2 + p {
    text-align: center;
    color: #546e7a;
    font-size: 10pt;
}

h1:first-of-type + h2 + p + p {
    text-align: center;
    color: #546e7a;
    font-size: 10pt;
}

/* ===== HEADINGS ===== */
h1 {
    font-size: 22pt;
    color: #0d47a1;
    border-bottom: 2px solid #1565c0;
    padding-bottom: 6px;
    margin-top: 30px;
    page-break-before: always;
}

h2 {
    font-size: 16pt;
    color: #1565c0;
    border-bottom: 1px solid #bbdefb;
    padding-bottom: 4px;
    margin-top: 26px;
    page-break-after: avoid;
}

h3 {
    font-size: 12pt;
    color: #1976d2;
    margin-top: 18px;
    page-break-after: avoid;
}

h4 {
    font-size: 11pt;
    color: #1e88e5;
    margin-top: 14px;
}

/* ===== TABLE OF CONTENTS ===== */
/* Style the TOC section */
h2#table-of-contents,
h2:nth-of-type(1) {
    page-break-before: always;
}

/* ===== TABLES ===== */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 14px 0;
    font-size: 9pt;
    page-break-inside: auto;
}

thead {
    display: table-header-group;
}

tr {
    page-break-inside: avoid;
    page-break-after: auto;
}

th {
    background-color: #0d47a1;
    color: white;
    padding: 8px 10px;
    text-align: left;
    font-weight: 600;
    font-size: 9pt;
}

td {
    padding: 6px 10px;
    border-bottom: 1px solid #e0e0e0;
    vertical-align: top;
}

tr:nth-child(even) td {
    background-color: #f5f8fc;
}

tr:hover td {
    background-color: #e3f2fd;
}

/* ===== CODE BLOCKS ===== */
pre {
    background-color: #263238;
    color: #eeffff;
    padding: 14px 16px;
    border-radius: 6px;
    font-size: 8.5pt;
    line-height: 1.5;
    overflow-x: auto;
    page-break-inside: avoid;
    margin: 12px 0;
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
}

code {
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
    font-size: 9pt;
}

p code, li code, td code {
    background-color: #e8eaf6;
    color: #283593;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 8.5pt;
}

/* ===== LISTS ===== */
ul, ol {
    margin: 8px 0;
    padding-left: 24px;
}

li {
    margin-bottom: 4px;
}

/* ===== LINKS ===== */
a {
    color: #1565c0;
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

/* ===== BLOCKQUOTES ===== */
blockquote {
    border-left: 4px solid #1976d2;
    background-color: #e3f2fd;
    padding: 10px 16px;
    margin: 12px 0;
    border-radius: 0 4px 4px 0;
}

/* ===== HORIZONTAL RULES ===== */
hr {
    border: none;
    border-top: 1px solid #cfd8dc;
    margin: 20px 0;
}

/* ===== PARAGRAPHS ===== */
p {
    margin: 8px 0;
    text-align: justify;
}

/* ===== STRONG / BOLD ===== */
strong {
    color: #0d47a1;
}

/* ===== PREVENT ORPHANS ===== */
h2, h3, h4 {
    page-break-after: avoid;
}

p, li {
    orphans: 3;
    widows: 3;
}

/* ===== JSON blocks ===== */
.highlight {
    background-color: #263238;
    border-radius: 6px;
}
"""

# Build full HTML document
html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>DigiHMS - Technical Documentation</title>
</head>
<body>
{html_body}
</body>
</html>"""

# Generate PDF
print("Generating PDF...")
HTML(string=html_doc).write_pdf(
    PDF_FILE,
    stylesheets=[CSS(string=css)],
)

print(f"PDF generated successfully: {PDF_FILE}")
print(f"File size: {os.path.getsize(PDF_FILE) / 1024:.1f} KB")
