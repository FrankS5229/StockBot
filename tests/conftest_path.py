"""讓 tests/ 內的腳本能 import 專案根目錄的模組。

每個 test 檔開頭 `import tests.conftest_path` 即可（或用 pytest 從專案根目錄執行）。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
