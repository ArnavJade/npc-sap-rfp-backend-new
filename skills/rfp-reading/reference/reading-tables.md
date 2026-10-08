# Reading tables, matrices and transcribed images

Scope matrices, phase lists, system inventories and integration diagrams are very often tables or
pasted images. This is how they appear in the `/rfp/` Markdown and how to read them.

## How the workspace represents them

- **Native tables** are pipe tables (`| a | b |`). They were extracted mechanically and can be
  imperfect, especially from PDFs (see the rules below).
- **Embedded images** (a matrix or diagram pasted in as a picture, a scanned page, a spreadsheet
  screenshot) are transcribed between `[EMBEDDED IMAGE -- p.N]` and `[END EMBEDDED IMAGE]`. Older
  extractions may also wrap a table between `[EXTRACTED TABLE -- <location>]` and
  `[END EXTRACTED TABLE]`.
- These markers appear only where the source document actually contained an embedded table or image
  at that position; their absence just means ordinary native text.

Treat everything inside an image or table block with exactly the same weight as surrounding narrative
text: a country/module relationship, a third-party system requiring SAP integration, a phase list or
a scope statement shown only in a transcribed image is just as real as one stated in plain text, and
must not be treated as less reliable or skipped. Walk every row - do not stop after the first few, and
do not summarise or sample a long table.

## How images were transcribed (so you know what to expect)

The transcriber was told to:

1. Transcribe ALL visible text verbatim - every label, header, footnote and number.
2. Reconstruct any table or matrix (especially a country x module / capability matrix) as a markdown
   table, every row and column exactly as shown, with marks (X, check mark, filled cell, "Yes")
   transcribed against their row and column.
3. Preserve country names, country codes, and SAP module/solution names exactly as written.
4. For an architecture, interface or integration diagram, write NO prose - instead one line per
   connection/edge, in the form

   ```
   <System/Tool A> <-> <System/Tool B, or the SAP module/process/component it connects to> : <label, purpose, or technical detail on that connection, verbatim>
   ```

   e.g. `REST <-> SAP FI/CO : Real-time RFC interfaces (SAP side)`,
   `Coupa <-> SAP (Treasury / Cash / Bank)`, `Data Lake (AWS) <-> SAP (reporting feeds)`.
   The `<->` is only the line format - it does NOT mean the interface is bidirectional; read
   direction from the label text ("Inbound", "Outbound", arrows described in the label). A line with
   no ` : <detail>` part had no label on the diagram.
   Other diagrams (org charts, timelines, generic process flows) are described node by node in plain
   sentences, quoting each label.
5. Say plainly when an image is decorative (logo, banner, divider) - such a block carries no scope.

A transcription can still miss a cropped edge; the block may end with a short note saying so.

## Rules for reading tables

- **A row belongs to its group.** An object, system or module belongs to the area whose table rows
  list it - never move it to another area because its name fits that area better (e.g. a tax master
  listed under Order to Cash stays under Order to Cash).
- **A cell naming several items is several items.** "House Bank, Bank keys" is two entries; "Coupa,
  Solver, Data Lake(AWS)" is three systems.
- **Merged cells.** A group label (module, area, domain, country) is often written only on the FIRST
  row of its group, with the cells below it empty; those rows belong to the same group until the next
  non-empty label in that column or an empty separator row. Carry labels down.
- **Padding columns.** Ignore empty padding columns; labels may shift between columns from row to
  row.
- **Split tables.** A long table can be split into consecutive blocks (often across pages), each
  repeating the ORIGINAL table's first row as its header. A repeated first row that is really a data
  row is NOT a header and does not label the rows under it - they continue the groups of the previous
  block.
- **Flattened duplicates.** A table's content can also appear as flattened plain text next to the
  table, where a merged label may sit beside the middle of its group rather than its first row. Take
  the grouping from the table itself; use the plain text only to judge where an ambiguous group ends.
- **Hyphenation.** Words broken across lines with a hyphen ("Mainte- nance") are one word
  ("Maintenance").
- **Matrices.** Read a country x module (or unit x module) matrix row by row: a country takes only
  the columns marked in its own row. Quote the header cells and the row as evidence.
- **Completeness.** For every list you extract from, walk it row by row and check the count before
  writing; list each entry once even when the RFP names it in several places, but never merge or drop
  genuinely different entries.
- **Table versus prose.** When a table and the surrounding prose disagree on a figure, prefer the
  table.

## Quoting from tables

The evidence check ignores case, spacing and punctuation (pipes included) and accepts the words of a
phrase in order within a short window, so a quote may run across the cells of one row. Quote one row
or one cell at a time - not a whole table, and never across a `<!-- page: N -->` marker.
