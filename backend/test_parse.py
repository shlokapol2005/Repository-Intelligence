import sys
import json
import argparse
from pathlib import Path

# Add current directory to path so it can import utils.parser
sys.path.append(str(Path(__file__).parent.resolve()))

from utils.parser import parse_file
from utils.scanner import scan_repository, read_file_content

def main():
    parser = argparse.ArgumentParser(description="Parse code files and dump AST extraction results.")
    parser.add_argument("--repo", type=str, default=".", help="Repository path to scan and parse")
    parser.add_argument("--out", type=str, default="parsing_result.json", help="Output JSON file")
    
    args = parser.parse_args()
    repo_path = Path(args.repo).resolve()
    
    print(f"Scanning repository: {repo_path}")
    files = scan_repository(str(repo_path))
    results = []
    
    for f in files:
        content = read_file_content(f["path"])
        parsed = parse_file(f["path"], content)
        # Adding relative path for better readability in the output
        parsed["relative_path"] = f["relative_path"]
        results.append(parsed)
        
    output_file = Path(__file__).parent / args.out
    output_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Parsed {len(files)} files.")
    print(f"Wrote output to {output_file}")

if __name__ == "__main__":
    main()
