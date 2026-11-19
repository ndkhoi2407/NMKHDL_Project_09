# Milestone 2 source module

This package parses the local Milestone 1 corpus into Milestone 2 records and
tables. The input corpus and generated outputs live outside this source folder;
the module does not bundle or regenerate them during a Jupyter Book build.

`cli.py` accepts `--output` for the existing Milestone 1 data directory and
`--parsed-output` for Milestone 2 results. Keep these paths pointed at the local
data workspace when running the parser. The report site only executes its
notebooks and does not invoke this data-processing CLI.
