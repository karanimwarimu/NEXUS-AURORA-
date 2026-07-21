import os, subprocess, sys

PY = sys.executable
CODE = (
    "import sys, os; "
    "sys.path.insert(0, r'F:\\DSF\\stsh projects\\NEXUS AURORA\\Nexora application\\Crawler'); "
    "import nexora_crawler.settings as s; "
    "print('DB    :', s.NEXORA_METADATA_DB); "
    "print('CHROMA:', s.NEXORA_CHROMA_PATH); "
    "print('env DB:', os.environ.get('NEXORA_METADATA_DB')); "
    "print('env CH:', os.environ.get('NEXORA_CHROMA_PATH'))"
)
CWDS = [
    r"F:\DSF\stsh projects\NEXUS AURORA\Nexora application\Crawler",
    r"F:\DSF\stsh projects\NEXUS AURORA\Nexora application\Crawler\nexora_crawler",
    r"F:\DSF\stsh projects\NEXUS AURORA",
]
results = []
for cwd in CWDS:
    out = subprocess.run([PY, "-c", CODE], cwd=cwd, capture_output=True, text=True)
    print(f"--- CWD: {cwd}")
    print(out.stdout.strip())
    results.append(out.stdout.strip())
print("\nALL IDENTICAL ACROSS CWDs:", len(set(results)) == 1)
