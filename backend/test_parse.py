import sys
import json
from pathlib import Path

# Add current directory to path so it can import utils.parser
sys.path.append(str(Path(__file__).parent.resolve()))

from utils.parser import parse_file

test_file = str(Path(__file__).parent / "routers" / "mcp.py")
content = Path(test_file).read_text(encoding="utf-8")

result = parse_file(test_file, content)

output_file = str(Path(__file__).parent / "parsing_result.json")
Path(output_file).write_text(json.dumps(result, indent=2), encoding="utf-8")
print("Wrote output to", output_file)
