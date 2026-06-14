"""
run_nexora.py
=============
Force-reload spider without .pyc cache issues.
Run this INSTEAD of 'scrapy crawl nexora'.
"""

import sys
import os

# Force Python to ignore .pyc files and recompile
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITITEBYTECODE"] = "1"

# Clear any existing cache
import shutil
project_root = os.path.dirname(os.path.abspath(__file__))
for root, dirs, files in os.walk(os.path.join(project_root, "nexora_crawler")):
    if "__pycache__" in dirs:
        pycache_path = os.path.join(root, "__pycache__")
        print(f"Removing: {pycache_path}")
        shutil.rmtree(pycache_path)
    for f in files:
        if f.endswith(".pyc"):
            pyc_path = os.path.join(root, f)
            print(f"Removing: {pyc_path}")
            os.remove(pyc_path)

# Now run scrapy with fresh imports
from scrapy.cmdline import execute

# Pass through all arguments after the script name
args = ["scrapy", "crawl", "nexora"] + sys.argv[1:]
print(f"Running: {' '.join(args)}")
execute(args)
