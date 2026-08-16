"""CycleBeat DE core.

The business logic of the offline pipeline. Airflow tasks in `dags/` are one-line calls
into this package and hold no logic of their own (E.5); the CLI in `cyclebeat.cli` runs
the same functions without a scheduler, which is what `make ingest` exercises.
"""
