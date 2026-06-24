import sys
from pathlib import Path

# Add Crawler/ to path so 'nexora_crawler' resolves
CRAWLER_ROOT = Path(__file__).resolve().parent.parent / "Crawler"
sys.path.insert(0, str(CRAWLER_ROOT))

# pytest-asyncio config
pytest_plugins = ("pytest_asyncio",)