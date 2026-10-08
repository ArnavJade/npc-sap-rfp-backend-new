# Reading migration tables

`[EXTRACTED TABLE]` blocks are extracted mechanically and can be imperfect, especially from PDFs:
- An object belongs to the area whose table rows list it - never move it to another area because its
  name fits that area better (a tax master listed under Order to Cash stays under Order to Cash).
- A cell naming several objects ("House Bank, Bank keys") is one entry per object.
- MERGED CELLS: a group label (module, area, domain) is often written only on the FIRST row of its
  group, with the cells below empty; those rows belong to the same group until the next non-empty
  label in that column or an empty separator row. Carry labels down.
- Ignore empty padding columns; labels may shift between columns from row to row.
- SPLIT TABLES: a long table can be split into consecutive blocks, each repeating the ORIGINAL
  table's first row as its header. A repeated first row that is really a data row is NOT a header
  and does not label the rows under it - they continue the groups of the previous block.
- A table's content can also appear as flattened plain text next to the block, where a merged label
  may sit beside the middle of its group. Take the grouping from the `[EXTRACTED TABLE]` block; use
  the plain text only to judge where an ambiguous group ends.
- Words broken across lines with a hyphen ("Mainte- nance") are one word ("Maintenance").
