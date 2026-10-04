# Internship Master List

One searchable list of internships and co-ops, gathered from public job boards
and from company career sites, with duplicates merged.

**The list is at https://neal-dandrea.github.io/internship-master-list/**

It refreshes four times a day. You can filter by degree level (PhD, MS), field,
region, how recently a role was posted, and whether it is a co-op.

## Where the listings come from

**Job boards.** SimplifyJobs, vanshb03, speedyapply, zapplyjobs, TanhJK728, the
PhD Intern Board by dion-jy, Northwestern Fintech, TrakkerHQ and OpenQuant.
Credit for the curation belongs to them.

**Company career sites.** Every link a board points at shows which careers
platform that company uses. The company is then remembered in
`data/companies.json`, and its own feed is read on every run. Six platforms are
supported, which are Workday, Greenhouse, Ashby, Lever, SmartRecruiters and
Workable. This is how a role can show up here before any board lists it.

## What the tags mean

Tags describe a posting. They are guesses made from the title and from what each
board reports, so read the posting before relying on them.

- **PhD** and **MS** mean the title or a board says the role is for that level
- **Co-op** means the title says so
- **Robotics, AI/ML, Research, Quant, Software, Data, Hardware** come from words
  in the title
- **US, International, Remote** come from the location text

## Running it yourself

It needs Python 3 and PyYAML.

```bash
python3 collect.py                 # boards and career sites, about a minute
python3 collect.py --no-careers    # boards only, a few seconds
python3 collect.py --only simplify,openquant
```

| File | What it holds |
|---|---|
| `docs/data.json` | Every active listing. The page reads this |
| `docs/listings.csv` | The same list for a spreadsheet |
| `data/seen.json` | The day each listing was first seen |
| `data/companies.json` | The career sites to check |
| `out/new_<date>.md` | What appeared since the last run. Not committed |

## How it decides things

- **Duplicates.** Two rows are one posting when their links match after tracking
  parameters are removed, or when they come from different sources and the
  company and title match. Rows from the same source are never merged by name,
  because a company can list one title many times for different teams.
- **Career site listings.** A company feed returns every internship in every
  department, so a listing found only there is kept when its title matches one
  of the technical fields and it is under 180 days old. Board listings are kept
  as the board lists them.
- **Failures.** A board or company site that fails is skipped for that run and
  its earlier listings are kept, so an outage does not make postings vanish.
- **Dates.** The date is the day a source says the role was posted. When no
  source gives one, it is the day the role was first seen here.

## Adding a source

A board is one function in `collect.py` that returns listings in the common
shape, plus one line in `SOURCES`. A careers platform is one function in
`ats.py`, plus one line in `READERS` and a link pattern in `_PATTERNS`.
