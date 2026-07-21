#nexora_crawler/pipelines/parquet_export.py
#Priority: 450 (after Phase 4B at 250, before standard export at 500)
#Purpose: Export data as compressed Apache Parquet files.
# ParquetExportPipeline — Phase 4A Analytical Storage
# Exports crawled data as compressed Apache Parquet files.
# Priority: 450

import json
import logging
import os
from datetime import datetime, timezone

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)


class ParquetExportPipeline:
    """
    Scrapy pipeline exporting data as Apache Parquet.
    Buffers rows and flushes to disk in batches.
    """

    def __init__(self, crawler):
        self.crawler = crawler
        self.settings = crawler.settings
        self.enabled = self.settings.getbool('NEXORA_PARQUET_ENABLED', True)
        self.compression = self.settings.get('NEXORA_PARQUET_COMPRESSION', 'snappy')
        self.row_group_size = self.settings.getint('NEXORA_PARQUET_ROW_GROUP_SIZE', 10000)
        self.output_dir = self.settings.get('NEXORA_PARQUET_OUTPUT', './output/parquet')

        self._buffer = []
        self._buffer_size = 100  # Flush every 100 items to match Phase 4A batch sizing
        self._total_rows = 0
        self._file_counter = 0
        self._spider_name = "nexora"  # default

    @classmethod
    def from_crawler(cls, crawler):
        obj = cls(crawler)
        obj.crawler = crawler
        return obj

    def open_spider(self):
        spider = getattr(self.crawler, 'spider', None)
        self._spider_name = getattr(spider, 'name', 'nexora') if spider else 'nexora'
        if not self.enabled:
            return
        os.makedirs(self.output_dir, exist_ok=True)
        logger.info("[Parquet] Export enabled — dir: %s", self.output_dir)

    async def process_item(self, item):
        if not self.enabled:
            return item

        row = self._item_to_parquet_row(item)
        self._buffer.append(row)

        if len(self._buffer) >= self._buffer_size:
            self._flush_buffer()

        return item

    def close_spider(self):
        if not self.enabled:
            return
        if self._buffer:
            self._flush_buffer()
        logger.info("[Parquet] Total rows exported: %d", self._total_rows)

    def _item_to_parquet_row(self, item: dict) -> dict:
        row = dict(item)

        # Serialize nested structures to JSON strings
        for key in ['entities', 'style_analysis', 'quality_scores',
                    'image_assets', 'video_assets', 'ai_tags', 'ai_embedding']:
            if key in row and not isinstance(row[key], str):
                row[f"{key}_json"] = json.dumps(row[key])
                del row[key]

        # Remove heavy / non-serializable fields (stored separately elsewhere)
        # `chunks` holds NexoraChunk dataclass objects — excluded so the
        # Arrow/Parquet conversion doesn't fail.
        for key in ['html', 'markdown', 'clean_text', 'chunks']:
            row.pop(key, None)

        # Catch-all: JSON-stringify any remaining dict/list field (meta_tags,
        # headings, links, structured_schema, ...). An all-empty dict column
        # would otherwise make PyArrow infer a struct with no child fields,
        # which Parquet cannot write ("Cannot write struct type ... no child
        # field") and the whole flush is lost.
        for key in list(row.keys()):
            if isinstance(row[key], (dict, list, tuple, set)):
                try:
                    row[f"{key}_json"] = json.dumps(row[key], default=str)
                except (TypeError, ValueError):
                    row[f"{key}_json"] = json.dumps(str(row[key]))
                del row[key]

        return row

    def _flush_buffer(self):
        if not self._buffer:
            return

        try:
            df = pd.DataFrame(self._buffer)
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            filename = f"{self._spider_name}_{timestamp}_{self._file_counter:04d}.parquet"
            filepath = os.path.join(self.output_dir, filename)

            table = pa.Table.from_pandas(df)
            pq.write_table(
                table,
                filepath,
                compression=self.compression,
                row_group_size=self.row_group_size,
                use_dictionary=True,
                write_statistics=True,
            )

            self._total_rows += len(self._buffer)
            self._file_counter += 1
            logger.info("[Parquet] Wrote %d rows to %s", len(self._buffer), filename)
            self._buffer = []

        except Exception as exc:
            logger.error("[Parquet] Flush failed: %s", exc)


"""
Spider Yields:
┌─────────────────────────────────────────┐
│  Item {                                 │
│    url: "https://...",                   │
│    title: "Hello",                       │
│    entities: {person: ["Alice"]},        │
│    html: "<html>...",                    │
│    markdown: "# Hello...",               │
│  }                                       │
└─────────────────────────────────────────┘
            ↓ process_item()
┌─────────────────────────────────────────┐
│  _item_to_parquet_row() transforms:     │
│    entities → entities_json: '{"person": │
│               ["Alice"]}'                │
│    html → REMOVED                       │
│    markdown → REMOVED                   │
│  Result: flat, JSON-stringified dict    │
└─────────────────────────────────────────┘
            ↓ append to _buffer
┌─────────────────────────────────────────┐
│  _buffer = [row1, row2, ..., row100]    │
│  len == 100? → _flush_buffer()          │
└─────────────────────────────────────────┘
            ↓ _flush_buffer()
┌─────────────────────────────────────────┐
│  pd.DataFrame(_buffer)                  │
│  → PyArrow Table                        │
│  → pq.write_table()                     │
│  → spider_20250630_211745_0000.parquet  │
└─────────────────────────────────────────┘
            ↓ return item
Next pipeline receives the original item

"""