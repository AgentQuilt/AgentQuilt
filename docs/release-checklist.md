# Release checklist

Run before every tag. Each line is done or the tag waits.

- [ ] Run the `scrub-gate` skill over every file the tag carries, by hand, and fix each hit at its source before re-running. The skill exits 0 or nothing crosses.
- [ ] Read every new public file by eye against the register the skill prints. A grep catches listed words only; judgement catches the rest. Record the reader's name and the date below.
- [ ] Name the green Actions run on `main` the release is cut from, by its run id.

## Record

One line per release: version, date, the Actions run id, the name of the person who read the files.
