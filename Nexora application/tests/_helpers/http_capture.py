import json
from pathlib import Path


class HTTPCapture:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records = []

    def record(self, method: str, url: str, status: int, body: str = "") -> None:
        self._records.append({"method": method, "url": url, "status": status, "body": body})

    def flush(self) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            for record in self._records:
                fh.write(json.dumps(record) + "\n")
