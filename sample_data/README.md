# Demo sample

A small extract of real BASt data, used by the app when the full data
is not installed. Built with `python scripts/make_sample.py` from the
full 2023 data. Values are copied unchanged; only rows and columns were
removed.

- Hourly counts: stations 9033 (AD Seligenstadt), 9040 (AK Nürnberg) and
  9093 (AK Deggendorf), 1 March to 30 June 2023, columns the app uses
  plus the BASt quality flags (`K_KFZ_R1`, `K_KFZ_R2`).
- `Jawe2023.csv`: the 46 A3 stations in Bavaria, with the station and
  destination names repaired as described in the main README.

Source: Bundesanstalt für Straßenwesen (BASt), automatic traffic counts
on federal motorways (hourly values) and the yearly evaluation file
(Jawe2023). The licence terms for redistribution have not been
confirmed; see the main README.
