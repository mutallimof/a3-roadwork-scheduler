# Data licence and source

The traffic data in this repository comes from the
**Bundesanstalt für Straßenwesen (BASt), automatische Dauerzählstellen**
(automatic permanent counting stations on federal motorways).

Licence: **Datenlizenz Deutschland – Namensnennung – Version 2.0**
(<https://www.govdata.de/dl-de/by-2-0>).

Source: Bundesanstalt für Straßenwesen (BASt), automatische Dauerzählstellen,
hourly values ("Stundenwerte") 2018, 2022 and 2023 and the yearly
evaluation file Jawe2023, <https://www.bast.de>.

This project is not affiliated with BASt, and BASt does not endorse it.

## Which files

| Path | Content |
|---|---|
| `2018/`, `2022/`, `2023/` | Hourly counts, one file per station and year (`zst<station>_<year>.csv`): 28, 16 and 19 stations, 551,880 rows |
| `Jawe2023.csv` | Station list: coordinates, direction names and other attributes of the counting stations |
| `sample_data/` | A small extract of the files above (3 stations, March–June 2023) for the demo mode |

## Changes made to the original files

- **Hourly counts:** the downloaded files were unzipped, taken out of
  per-station subfolders, renamed to `zst<station>_<year>.csv` and placed
  in one folder per year. Only rows for the A3 in Bavaria were kept (all
  rows in the files used are Land 09, road A3). The values themselves are
  unchanged: every row and column is as in the source file.
- **Jawe2023.csv:** reduced from 2,116 rows (all of Germany) to the 46
  stations on the A3 in Bavaria; all columns are kept. In the copy that was
  available, every umlaut had been replaced by an unknown-character mark.
  16 station names were repaired from the Jawe2022 names printed in
  `analysis.ipynb` (`station_names.csv`), and only where the station
  number matches and every other letter is identical. Other text was
  repaired word by word where exactly one known name fits (e.g. Nürnberg,
  Würzburg). 10 values in the columns `Nahziel_Ri1`, `Nahziel_Ri2` and
  `Anmerkungen` could not be checked and contain `?` in place of the lost
  letter. These columns are not used by the app.
- **sample_data/:** only rows and columns were removed; the station names
  are the repaired ones.

The changes are made by `scripts/fetch_data.py` and
`scripts/make_sample.py`, so they can be repeated from the original files.
