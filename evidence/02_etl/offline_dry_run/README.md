# Pre-database dry run (synthetic data)

Produced by `python -m src.offline_dry_run` before the databases were available. It runs the pure-Python ETL (profile, normalize, crosswalks, quality, dimensions, facts) on the generated sources and checks the results against the generator's defect ledger and stage-2 change list. The official evidence of units 2.02-3.06 is produced later from the databases.
