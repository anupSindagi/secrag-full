import re
import warnings
from io import StringIO
from typing import Dict, List, Optional, Tuple

import pandas as pd
import sec_parser as sp
import tiktoken
from bs4 import BeautifulSoup

GPT4_ENCODING = "cl100k_base"
tokenizer = tiktoken.get_encoding(GPT4_ENCODING)


def count_tokens(text: str) -> int:
    return len(tokenizer.encode(text))


def get_level(elem_type: str) -> int:
    match = re.search(r"\[L(\d+)\]", elem_type)
    return int(match.group(1)) if match else -1


def unmerge_table_cells(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for td in soup.find_all("td"):
        if td.has_attr("colspan"):
            colspan = int(td.get("colspan", 1))
            if colspan > 1:
                for _ in range(colspan - 1):
                    new_td = soup.new_tag("td")
                    new_td.string = "NaN"
                    td.insert_before(new_td)
                td["colspan"] = "1"
    return str(soup)


def clean_table_html(html_content: str) -> str:
    soup = BeautifulSoup(html_content, "lxml")
    table = soup.find("table")
    if not table:
        return html_content

    clean_table = soup.new_tag("table")
    for tr in table.find_all("tr"):
        clean_tr = soup.new_tag("tr")
        for cell in tr.find_all(["td", "th"], recursive=False):
            cell_text = cell.get_text(separator=" ", strip=True)
            clean_cell = soup.new_tag(cell.name)
            clean_cell.string = cell_text
            if "colspan" in cell.attrs:
                clean_cell["colspan"] = cell["colspan"]
            if "rowspan" in cell.attrs:
                clean_cell["rowspan"] = cell["rowspan"]
            clean_tr.append(clean_cell)
        if clean_tr.contents:
            clean_table.append(clean_tr)
    return str(clean_table)


def table_html_to_markdown(html_content: str) -> Optional[str]:
    try:
        unmerged_html = unmerge_table_cells(html_content)
        dfs = pd.read_html(StringIO(unmerged_html), flavor="lxml")
        if not dfs:
            return None

        df = dfs[0].dropna(how="all").dropna(axis=1, how="all").fillna("")
        markdown_table = df.to_markdown(index=False)
        return re.sub(r" +", " ", markdown_table)
    except Exception:
        return None


def get_table_html(element) -> Optional[str]:
    methods = [
        lambda: element.get_source_code() if hasattr(element, "get_source_code") else None,
        lambda: str(element.html_tag) if hasattr(element, "html_tag") and element.html_tag else None,
        lambda: str(element._html_tag) if hasattr(element, "_html_tag") and element._html_tag else None,
        lambda: str(element.tag) if hasattr(element, "tag") and element.tag else None,
    ]
    for method in methods:
        try:
            html_content = method()
            if html_content:
                return html_content
        except Exception:
            continue
    return None


def create_parser_for_form(form_type: str = "10-Q"):
    if form_type.upper() == "10-Q":
        return sp.Edgar10QParser()

    from sec_parser.processing_steps import (
        IndividualSemanticElementExtractor,
        TopSectionManagerFor10Q,
        TopSectionTitleCheck,
    )

    def without_10q_steps():
        all_steps = sp.Edgar10QParser().get_default_steps()
        steps_without_top_section = [
            step for step in all_steps if not isinstance(step, TopSectionManagerFor10Q)
        ]

        def get_checks_without_top_section():
            all_checks = sp.Edgar10QParser().get_default_single_element_checks()
            return [
                check for check in all_checks if not isinstance(check, TopSectionTitleCheck)
            ]

        return [
            IndividualSemanticElementExtractor(get_checks=get_checks_without_top_section)
            if isinstance(step, IndividualSemanticElementExtractor)
            else step
            for step in steps_without_top_section
        ]

    return sp.Edgar10QParser(get_steps=without_10q_steps)


def extract_chunks_from_elements(elements: List, form_type: str = "10-Q") -> List[Dict]:
    del form_type
    chunks = []
    context_stack: List[Tuple[int, str]] = []

    for element in elements:
        elem_type = element.__class__.__name__
        level = get_level(elem_type)

        text_content = ""
        if hasattr(element, "text") and element.text:
            text_content = str(element.text).strip()

        if "TopSectionTitle" in elem_type and text_content:
            context_stack = [(level, text_content[:100])]
        elif "TitleElement" in elem_type and text_content:
            context_stack = [ctx for ctx in context_stack if ctx[0] < level]
            context_stack.append((level, text_content[:100]))

        if "TableElement" in elem_type:
            html_content = get_table_html(element)
            if not html_content:
                continue

            cleaned_html = clean_table_html(html_content)
            markdown_table = table_html_to_markdown(cleaned_html)
            context_parts = [ctx[1] for ctx in context_stack]
            context_str = " > ".join(context_parts) if context_parts else "root"
            content = markdown_table if markdown_table else cleaned_html
            content_type = "markdown" if markdown_table else "html"

            chunks.append(
                {
                    "type": "table",
                    "content": content,
                    "content_type": content_type,
                    "context": context_str,
                    "html": cleaned_html,
                    "tokens": count_tokens(content),
                }
            )

        elif "TextElement" in elem_type and text_content:
            context_parts = [ctx[1] for ctx in context_stack]
            context_str = " > ".join(context_parts) if context_parts else "root"
            chunks.append(
                {
                    "type": "text",
                    "content": text_content,
                    "content_type": "text",
                    "context": context_str,
                    "tokens": count_tokens(text_content),
                }
            )

    return chunks


def parse_sec_filing(html: str, form_type: str = "10-Q", url: Optional[str] = None) -> List[Dict]:
    parser = create_parser_for_form(form_type)

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Invalid section type for")
        elements = parser.parse(html)

    chunks = extract_chunks_from_elements(elements, form_type)
    metadata = {"form_type": form_type, "url": url or "unknown"}
    for chunk in chunks:
        chunk["metadata"] = metadata
    return chunks
