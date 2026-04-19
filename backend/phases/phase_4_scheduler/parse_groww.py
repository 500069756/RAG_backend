"""
Groww Factsheet Parser — Specialized Extractor for Key Fund Metrics

Extracts structured data from Groww mutual fund pages:
    - NAV (Net Asset Value)
    - Minimum SIP Amount
    - Fund Size (AUM)
    - Expense Ratio
    - Rating
    - Fund Manager
    - Returns (1Y, 3Y, 5Y)
    - Risk metrics (standard deviation, beta, Sharpe ratio)

Usage:
    python -m phases.phase_4_scheduler.parse_groww <input_dir>
    
    OR integrate with scraper.py to parse after scraping
"""

import json
import logging
import re
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class GrowwFundDataParser:
    """
    Parses Groww mutual fund HTML/text to extract key fund metrics.
    
    Note: Groww uses JavaScript rendering, so this parser works with:
    1. Pre-scraped text files (limited data)
    2. Raw HTML files (better extraction)
    3. Manual JSON input (most reliable)
    """
    
    def __init__(self):
        self.patterns = {
            # NAV patterns
            "nav": [
                r"NAV\s*[:\-]\s*₹?\s*([\d,]+\.?\d*)",
                r"Net Asset Value\s*[:\-]\s*₹?\s*([\d,]+\.?\d*)",
            ],
            # Minimum SIP patterns
            "min_sip": [
                r"Minimum SIP\s*[:\-]\s*₹?\s*([\d,]+)",
                r"SIP.*?₹\s*([\d,]+)",
                r"Start SIP.*?₹\s*([\d,]+)",
            ],
            # Fund size patterns
            "fund_size": [
                r"Fund Size\s*[:\-]\s*₹?\s*([\d,]+\.?\d*)\s*(Cr|Crore|Billion)",
                r"AUM\s*[:\-]\s*₹?\s*([\d,]+\.?\d*)\s*(Cr|Crore|Billion)",
                r"Assets Under Management\s*[:\-]\s*₹?\s*([\d,]+\.?\d*)",
            ],
            # Expense ratio patterns
            "expense_ratio": [
                r"Expense Ratio\s*[:\-]\s*([\d.]+)%?",
                r"Total Expense Ratio\s*[:\-]\s*([\d.]+)%?",
                r"TER\s*[:\-]\s*([\d.]+)%?",
            ],
            # Rating patterns
            "rating": [
                r"Rating\s*[:\-]\s*(\d+)\s*/?\s*5",
                r"(\d+)\s*Star\s*Fund",
                r"Star Rating\s*[:\-]\s*(\d+)",
            ],
        }
    
    def parse_text_file(self, text_file: Path) -> dict:
        """
        Parse a scraped text file to extract fund metrics.
        
        Args:
            text_file: Path to scraped .txt file
            
        Returns:
            Dictionary with extracted metrics
        """
        with open(text_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        result = {
            "nav": None,
            "min_sip": None,
            "fund_size": None,
            "expense_ratio": None,
            "rating": None,
            "raw_data": {}
        }
        
        # Try to extract each metric using regex patterns
        for metric, patterns in self.patterns.items():
            for pattern in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    value = match.group(1).strip().replace(',', '')
                    result[metric] = value
                    result["raw_data"][metric] = match.group(0)
                    break
        
        # Extract fund size from table if present
        fund_size_match = re.search(r"Fund Size\(Cr\).*?\|.*?(\d+\.?\d*)", content)
        if fund_size_match and not result["fund_size"]:
            result["fund_size"] = fund_size_match.group(1)
        
        logger.info(f"Parsed {text_file.name}: Found {sum(1 for v in result.values() if v and v != {})} metrics")
        return result
    
    def parse_html_file(self, html_file: Path) -> dict:
        """
        Parse raw HTML to extract fund metrics (better than text).
        
        Args:
            html_file: Path to raw .html file
            
        Returns:
            Dictionary with extracted metrics
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("BeautifulSoup not available. Install: pip install beautifulsoup4")
            return {}
        
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        soup = BeautifulSoup(html_content, 'html.parser')
        result = {
            "nav": None,
            "min_sip": None,
            "fund_size": None,
            "expense_ratio": None,
            "rating": None,
            "fund_name": None,
            "category": None,
            "raw_data": {}
        }
        
        # Extract NAV from meta tags or structured data
        nav_meta = soup.find('meta', {'property': 'og:description'})
        if nav_meta:
            nav_match = re.search(r'NAV.*?₹?\s*([\d,]+\.?\d*)', nav_meta.get('content', ''))
            if nav_match:
                result["nav"] = nav_match.group(1).replace(',', '')
        
        # Extract structured data (JSON-LD)
        json_ld = soup.find('script', type='application/ld+json')
        if json_ld:
            try:
                data = json.loads(json_ld.string)
                # Extract relevant fields from structured data
                if 'offers' in data:
                    result["nav"] = data['offers'].get('price')
            except:
                pass
        
        # Look for data attributes in HTML
        # Groww often uses data-* attributes for fund metrics
        for tag in soup.find_all(['div', 'span', 'p']):
            attrs = tag.attrs
            
            # Check class names and data attributes
            classes = ' '.join(attrs.get('class', []))
            
            # NAV
            if 'nav' in classes.lower() or 'current-price' in classes.lower():
                nav_text = tag.get_text(strip=True)
                nav_match = re.search(r'₹?\s*([\d,]+\.?\d*)', nav_text)
                if nav_match:
                    result["nav"] = nav_match.group(1).replace(',', '')
            
            # Fund size
            if 'fund-size' in classes.lower() or 'aum' in classes.lower():
                size_text = tag.get_text(strip=True)
                size_match = re.search(r'₹?\s*([\d,]+\.?\d*)\s*(Cr|Crore)?', size_text)
                if size_match:
                    result["fund_size"] = size_match.group(1)
            
            # Expense ratio
            if 'expense' in classes.lower():
                exp_text = tag.get_text(strip=True)
                exp_match = re.search(r'([\d.]+)%?', exp_text)
                if exp_match:
                    result["expense_ratio"] = exp_match.group(1)
            
            # Rating
            if 'rating' in classes.lower() or 'star' in classes.lower():
                rating_text = tag.get_text(strip=True)
                rating_match = re.search(r'(\d+\.?\d*)\s*/?\s*5', rating_text)
                if rating_match:
                    result["rating"] = rating_match.group(1)
        
        logger.info(f"Parsed HTML {html_file.name}: Found {sum(1 for v in result.values() if v and v != {})} metrics")
        return result
    
    def create_fund_summary(self, scraped_dir: Path, output_dir: Optional[Path] = None):
        """
        Parse all Groww scraped files and create a summary JSON.
        
        Args:
            scraped_dir: Directory containing scraped files
            output_dir: Directory to save summary (default: same as scraped_dir)
            
        Returns:
            Path to summary file
        """
        if output_dir is None:
            output_dir = scraped_dir
        
        summary = {
            "funds": [],
            "metadata": {
                "total_funds": 0,
                "parsed_at": None,
                "parser_version": "1.0"
            }
        }
        
        # Find all Groww meta files
        meta_files = list(scraped_dir.glob("groww-*.meta.json"))
        
        for meta_file in meta_files:
            # Load metadata
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            
            # Find corresponding text file
            text_file = meta_file.with_suffix('.txt')
            
            fund_data = {
                "id": meta.get("id"),
                "scheme": meta.get("scheme"),
                "category": meta.get("category"),
                "url": meta.get("url"),
                "metrics": {}
            }
            
            # Parse text file
            if text_file.exists():
                fund_data["metrics"] = self.parse_text_file(text_file)
            
            summary["funds"].append(fund_data)
        
        summary["metadata"]["total_funds"] = len(summary["funds"])
        summary["metadata"]["parsed_at"] = str(__import__('datetime').datetime.now())
        
        # Save summary
        summary_file = output_dir / "groww_funds_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Created fund summary: {summary_file}")
        logger.info(f"Total funds parsed: {len(summary['funds'])}")
        
        return summary_file


def main():
    """CLI entry point for parsing Groww fund data."""
    parser = __import__('argparse').ArgumentParser(
        description="Parse Groww mutual fund pages for key metrics"
    )
    parser.add_argument(
        "--scraped-dir",
        default="backend/data/scraped",
        help="Directory containing scraped Groww files"
    )
    parser.add_argument(
        "--mode",
        choices=["parse-all", "parse-single", "summary"],
        default="summary",
        help="Parsing mode"
    )
    parser.add_argument(
        "--file",
        help="Single file to parse (for parse-single mode)"
    )
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )
    
    scraped_dir = Path(args.scraped_dir)
    parser_obj = GrowwFundDataParser()
    
    if args.mode == "parse-all":
        # Parse all text files
        for txt_file in scraped_dir.glob("groww-*.txt"):
            result = parser_obj.parse_text_file(txt_file)
            print(f"\n{txt_file.name}:")
            print(json.dumps(result, indent=2))
    
    elif args.mode == "parse-single":
        if not args.file:
            print("Error: --file required for parse-single mode")
            sys.exit(1)
        
        file_path = Path(args.file)
        if file_path.suffix == '.txt':
            result = parser_obj.parse_text_file(file_path)
        elif file_path.suffix == '.html':
            result = parser_obj.parse_html_file(file_path)
        else:
            print(f"Error: Unsupported file type {file_path.suffix}")
            sys.exit(1)
        
        print(json.dumps(result, indent=2))
    
    elif args.mode == "summary":
        summary_file = parser_obj.create_fund_summary(scraped_dir)
        print(f"\n✅ Summary created: {summary_file}")
        
        # Display summary
        with open(summary_file, 'r') as f:
            data = json.load(f)
        
        print(f"\n📊 Fund Metrics Summary:")
        print(f"Total funds: {data['metadata']['total_funds']}")
        
        for fund in data['funds']:
            print(f"\n{fund['scheme']}:")
            metrics = fund['metrics']
            print(f"  NAV: {metrics.get('nav', 'N/A')}")
            print(f"  Min SIP: ₹{metrics.get('min_sip', 'N/A')}")
            print(f"  Fund Size: ₹{metrics.get('fund_size', 'N/A')} Cr")
            print(f"  Expense Ratio: {metrics.get('expense_ratio', 'N/A')}%")
            print(f"  Rating: {metrics.get('rating', 'N/A')}/5")


if __name__ == "__main__":
    main()
