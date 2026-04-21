"""
sec_parser_test.py

Clean implementation for parsing SEC filings using sec_parser:
- Extracts text and table chunks with proper context
- Converts tables to markdown format (with unmerged cells)
- Includes token counting for chunking
- Supports multiple SEC form types (10-Q, 10-K, etc.)
"""

import json
import re
from typing import List, Dict, Optional, Tuple
from io import StringIO

# Import the sec-parser package (note: package name is sec-parser, imported as sec_parser)
import sec_parser as sp
import requests
import tiktoken
from bs4 import BeautifulSoup
import pandas as pd
import warnings


# =========================
# CONFIGURATION
# =========================

GPT4_ENCODING = "cl100k_base"
tokenizer = tiktoken.get_encoding(GPT4_ENCODING)

SEC_HEADERS = {
    'User-Agent': 'Company Name contact@example.com',
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov'
}


# =========================
# UTILITY FUNCTIONS
# =========================

def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken."""
    return len(tokenizer.encode(text))


def get_level(elem_type: str) -> int:
    """Extract level from element type string (e.g., 'TitleElement[L1]' -> 1)."""
    match = re.search(r'\[L(\d+)\]', elem_type)
    return int(match.group(1)) if match else -1


# =========================
# TABLE PROCESSING
# =========================

def unmerge_table_cells(html: str) -> str:
    """
    Unmerge table cells by expanding colspan attributes.
    Based on context from notebook 2.
    """
    soup = BeautifulSoup(html, 'lxml')
    
    for td in soup.find_all('td'):
        if td.has_attr('colspan'):
            colspan = int(td.get('colspan', 1))
            if colspan > 1:
                # Insert empty cells before this cell
                for _ in range(colspan - 1):
                    new_td = soup.new_tag('td')
                    new_td.string = "NaN"
                    td.insert_before(new_td)
                td['colspan'] = "1"
    
    return str(soup)


def clean_table_html(html_content: str) -> str:
    """Clean table HTML to keep only essential structure."""
    soup = BeautifulSoup(html_content, 'lxml')
    
    table = soup.find('table')
    if not table:
        return html_content
    
    clean_table = soup.new_tag('table')
    
    for tr in table.find_all('tr'):
        clean_tr = soup.new_tag('tr')
        
        for cell in tr.find_all(['td', 'th'], recursive=False):
            cell_text = cell.get_text(separator=' ', strip=True)
            
            clean_cell = soup.new_tag(cell.name)
            clean_cell.string = cell_text
            
            # Preserve colspan/rowspan
            if 'colspan' in cell.attrs:
                clean_cell['colspan'] = cell['colspan']
            if 'rowspan' in cell.attrs:
                clean_cell['rowspan'] = cell['rowspan']
            
            clean_tr.append(clean_cell)
        
        if clean_tr.contents:
            clean_table.append(clean_tr)
    
    return str(clean_table)


def table_html_to_markdown(html_content: str) -> Optional[str]:
    """
    Convert HTML table to markdown format.
    Unmerges cells and converts to pandas DataFrame first.
    """
    try:
        # Unmerge cells first
        unmerged_html = unmerge_table_cells(html_content)
        
        # Parse with pandas
        dfs = pd.read_html(StringIO(unmerged_html), flavor='lxml')
        if not dfs:
            return None
        
        df = dfs[0]
        
        # Remove completely empty rows and columns
        df = df.dropna(how='all').dropna(axis=1, how='all')
        df = df.fillna("")
        
        # Convert to markdown
        markdown_table = df.to_markdown(index=False)
        
        # Clean up extra spaces
        markdown_table = re.sub(r' +', ' ', markdown_table)
        
        return markdown_table
    except Exception as e:
        print(f"Warning: Could not convert table to markdown: {e}")
        return None


def get_table_html(element) -> Optional[str]:
    """Extract HTML from TableElement using multiple fallback methods."""
    html_content = None
    
    # Try different methods to get HTML
    methods = [
        lambda: element.get_source_code() if hasattr(element, 'get_source_code') else None,
        lambda: str(element.html_tag) if hasattr(element, 'html_tag') and element.html_tag else None,
        lambda: str(element._html_tag) if hasattr(element, '_html_tag') and element._html_tag else None,
        lambda: str(element.tag) if hasattr(element, 'tag') and element.tag else None,
    ]
    
    for method in methods:
        try:
            html_content = method()
            if html_content:
                break
        except Exception:
            continue
    
    return html_content


# =========================
# PARSER SETUP
# =========================

def create_parser_for_form(form_type: str = "10-Q"):
    """
    Create parser for different SEC form types.
    For non-10-Q forms, removes 10-Q specific steps.
    """
    if form_type.upper() == "10-Q":
        return sp.Edgar10QParser()
    
    # For other forms, remove 10-Q specific steps
    from sec_parser.processing_steps import (
        TopSectionManagerFor10Q,
        IndividualSemanticElementExtractor,
        TopSectionTitleCheck
    )
    
    def without_10q_steps():
        all_steps = sp.Edgar10QParser().get_default_steps()
        
        # Remove TopSectionManagerFor10Q
        steps_without_top_section = [
            step for step in all_steps
            if not isinstance(step, TopSectionManagerFor10Q)
        ]
        
        # Remove TopSectionTitleCheck from checks
        def get_checks_without_top_section():
            all_checks = sp.Edgar10QParser().get_default_single_element_checks()
            return [
                check for check in all_checks
                if not isinstance(check, TopSectionTitleCheck)
            ]
        
        # Replace IndividualSemanticElementExtractor
        return [
            IndividualSemanticElementExtractor(get_checks=get_checks_without_top_section)
            if isinstance(step, IndividualSemanticElementExtractor)
            else step
            for step in steps_without_top_section
        ]
    
    return sp.Edgar10QParser(get_steps=without_10q_steps)


# =========================
# CHUNK EXTRACTION
# =========================

def extract_chunks_from_elements(
    elements: List,
    form_type: str = "10-Q"
) -> List[Dict]:
    """
    Extract chunks from parsed SEC filing elements.
    
    Returns list of chunk dictionaries with:
    - type: "text" or "table"
    - content: text or markdown table
    - context: hierarchical context string
    - tokens: token count
    - html: (for tables) original HTML
    """
    chunks = []
    context_stack: List[Tuple[int, str]] = []  # Stack of (level, text) tuples
    
    for element in elements:
        elem_type = element.__class__.__name__
        level = get_level(elem_type)
        
        # Get text content
        text_content = ""
        if hasattr(element, 'text') and element.text:
            text_content = str(element.text).strip()
        
        # Update context stack for title elements
        if 'TopSectionTitle' in elem_type and text_content:
            # Top section - reset context stack
            context_stack = [(level, text_content[:100])]
        elif 'TitleElement' in elem_type and text_content:
            # Title element - update context stack
            # Remove items at same or deeper level
            context_stack = [ctx for ctx in context_stack if ctx[0] < level]
            context_stack.append((level, text_content[:100]))
        
        # Extract chunks for TableElement and TextElement
        if 'TableElement' in elem_type:
            html_content = get_table_html(element)
            
            if html_content:
                # Clean HTML
                cleaned_html = clean_table_html(html_content)
                
                # Convert to markdown
                markdown_table = table_html_to_markdown(cleaned_html)
                
                # Build context string
                context_parts = [ctx[1] for ctx in context_stack]
                context_str = " > ".join(context_parts) if context_parts else "root"
                
                # Use markdown if available, otherwise HTML
                content = markdown_table if markdown_table else cleaned_html
                content_type = "markdown" if markdown_table else "html"
                
                chunk = {
                    "type": "table",
                    "content": content,
                    "content_type": content_type,
                    "context": context_str,
                    "html": cleaned_html,
                    "tokens": count_tokens(content)
                }
                
                chunks.append(chunk)
        
        elif 'TextElement' in elem_type and text_content:
            # Build context string
            context_parts = [ctx[1] for ctx in context_stack]
            context_str = " > ".join(context_parts) if context_parts else "root"
            
            chunk = {
                "type": "text",
                "content": text_content,
                "content_type": "text",
                "context": context_str,
                "tokens": count_tokens(text_content)
            }
            
            chunks.append(chunk)
    
    return chunks


# =========================
# MAIN PIPELINE
# =========================

def download_sec_filing(url: str) -> Optional[str]:
    """Download SEC filing HTML from URL."""
    try:
        response = requests.get(url, headers=SEC_HEADERS, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error downloading filing: {e}")
        return None


def parse_sec_filing(
    html: str,
    form_type: str = "10-Q",
    url: Optional[str] = None
) -> List[Dict]:
    """
    Parse SEC filing HTML and extract chunks.
    
    Args:
        html: SEC filing HTML content
        form_type: Form type (10-Q, 10-K, etc.)
        url: Optional URL for metadata
    
    Returns:
        List of chunk dictionaries
    """
    # Create parser for form type
    parser = create_parser_for_form(form_type)
    
    # Parse with warnings suppressed for non-10-Q forms
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Invalid section type for")
        elements = parser.parse(html)
    
    # Extract chunks
    chunks = extract_chunks_from_elements(elements, form_type)
    
    # Add metadata to each chunk
    metadata = {
        "form_type": form_type,
        "url": url or "unknown"
    }
    
    for chunk in chunks:
        chunk["metadata"] = metadata
    
    return chunks


# =========================
# MAIN EXECUTION
# =========================

def main():
    """Main execution function."""
    # Example SEC filing URL
    sec_url = "https://www.sec.gov/Archives/edgar/data/874761/000087476123000039/aes-20230331.htm"
    
    print(f"Downloading SEC filing from: {sec_url}")
    html = download_sec_filing(sec_url)
    
    if not html:
        print("Failed to download filing")
        return
    
    print(f"✓ Successfully downloaded HTML ({len(html)} characters)")
    
    # Detect form type from URL or default to 10-Q
    form_type = "10-Q"  # Could be extracted from URL or HTML
    print(f"Parsing as {form_type}...")
    
    # Parse and extract chunks
    chunks = parse_sec_filing(html, form_type=form_type, url=sec_url)
    
    print(f"\n✓ Extracted {len(chunks)} chunks")
    
    # Print summary
    text_chunks = [c for c in chunks if c["type"] == "text"]
    table_chunks = [c for c in chunks if c["type"] == "table"]
    
    print(f"  - Text chunks: {len(text_chunks)}")
    print(f"  - Table chunks: {len(table_chunks)}")
    
    total_tokens = sum(c["tokens"] for c in chunks)
    print(f"  - Total tokens: {total_tokens:,}")
    
    # Save to JSON
    output_file = 'chunks.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Saved {len(chunks)} chunks to {output_file}")


if __name__ == "__main__":
    main()
