# Pre-#57 lake partitions

Two partitions in the lake format that existed before #57: `TIMESTAMP` columns hold the **local
wall time** of the process that wrote them, not UTC.

| file | rows | timestamp column | value |
|---|---|---|---|
| `raw/tracks/dt=2026-07-29/part.parquet` | 48 | `ingested_at` | `2026-07-29 17:43:42` |
| `raw/resolutions/dt=2026-07-29/part.parquet` | 88 | `resolved_at` | `2026-07-29 17:43:42` |

**Provenance.**
- The owner copied these files on 2026-10-29 from the real `lake/`; the agent may not read-copy out of `lake/`.
- The demo ingest wrote them on 2026-10-09 on a host in `Europe/Paris`. The snapshot's `generated_at`, `2026-07-29T17:43:42+0200`, is `15:43:42` UTC, and it was written as `17:43:42`.
- They are byte-identical to the originals:

```
52489248a5357c0f71f7feea48b434267a626a66ca703c98f46e3cf04a743856  raw/tracks/dt=2026-07-29/part.parquet
7670321737b3682c45487e11476d9ec8e004c2b8fdf00aae396ff3f039c59a63  raw/resolutions/dt=2026-07-29/part.parquet
```

**Use.** `tests/test_lake_utc.py` copies them into a lake under `tmp_path`, re-runs the demo
ingest for the same `dt` and checks that no row of this format is left. That is the re-extraction
the owner runs on the real lake after #57. These files are never rewritten.
