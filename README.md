# Internship Master List

One searchable list of internships and co-ops, gathered from public job boards
and from company career sites, with duplicates merged.

**The list is at https://neal-dandrea.github.io/internship-master-list/**

It refreshes every hour from 8 AM through 1 AM Eastern. You can filter by degree level (PhD, MS), field,
region, how recently a role was posted, experience asked, eligibility rules and
match score, and you can search by city, state or country.

## Where the listings come from

**Job boards.** SimplifyJobs, vanshb03, speedyapply, zapplyjobs, TanhJK728, the
PhD Intern Board by dion-jy, Northwestern Fintech, TrakkerHQ and OpenQuant.
Credit for the curation belongs to them.

**Company career sites.** Every link a board points at shows which careers
platform that company uses. The company is then remembered in
`data/companies.json`, and its own feed is read on every run. The supported
platforms are Workday, Oracle Cloud, iCIMS, Eightfold, UKG, Greenhouse, Ashby,
Lever, SmartRecruiters and Workable. An identifier that never answers is dropped
after a few runs.

**Careers pages with no feed.** Many employers and platforms publish no feed at
all. For a number of them, the request their own careers page makes when an
ordinary visitor opens it was worked out and is used here, with no login. That
covers the platforms in `platforms.py` (Rippling, BambooHR, Pinpoint, Breezy,
Recruitee, Teamtailor, Personio, Gem, Dover, Paylocity, JazzHR, Jobvite, SAP
SuccessFactors, Phenom, Radancy, Avature and Taleo) and a few employers with
software of their own (TikTok, ByteDance, Amazon, Apple, IBM and D. E. Shaw).
None of these is a published feed, so any of them can stop working without
notice. A site that refuses automated visitors is left alone and listed on the
"Check by hand" tab instead.

Some employers run a known platform under their own address, so a posting link
does not show which one. A few such addresses are tested on each run, and the
results are kept in `data/probed.json`. This is how a role can show up here before any board lists it.

## The other two tabs

**Not posted yet.** For each company that posted internships last summer, this
shows the day its first listing appeared then and what it has posted so far this
year. Companies tend to open at about the same time each year, so that day, one
year on, is a rough guide to when to look. The history comes from older copies
of the SimplifyJobs data file, read once by `history.py` into
`data/history.json`. It is a guide and not a promise.

**Check by hand.** Some employers run their careers pages on their own software,
or on a platform there is no reader for, so their openings cannot be pulled in.
They are logged here with a link. The list is built on every run from job board
listings that point at such a site, with a count of the postings seen, plus the
employers named in `data/manual.json` and any career site whose feed has stopped
answering. The code is in `manual.py`.

## What the tags mean

Tags describe a posting. They are guesses made from the title and from what each
board reports, so read the posting before relying on them.

- **PhD** and **MS** mean the title or a board says the role is for that level
- **Co-op** means the title says so
- **Robotics, AI/ML, Research, Quant, Software, Data, Hardware** come from words
  in the title
- **US, International, Remote** come from the location text

## The match score

Each listing carries a score from 0 to 100 that compares the posting with the
maintainer's resumes. It is personal to the maintainer, so treat it as their
view of the list and not as a rating of the job.

1. The posting's description is read once and reduced to the skills and topics
   it mentions, using the vocabulary in `skills.py`.
2. Each resume is reduced to its skills and topics the same way.
3. The score is how much of what the posting mentions is on the resume. Rare,
   specific skills count for more than common ones, and a posting that says
   very little is pulled toward the middle so that two matching words do not
   outrank ten of twelve.

When there are several resumes, a listing takes its best score and names the
resume that produced it. When a description cannot be read, the score comes
from the title alone and is shown with a dashed outline.

The resumes are not in this repository. The scoring run reads a private profile
from a repository secret, and only the number and the resume's name are
published.

## The meaning score

The keyword score only sees words from a fixed vocabulary. A second score reads
meaning. It uses a small open-source embedding model (BAAI/bge-small-en-v1.5,
run on the CPU through the fastembed library), which places sentences with
similar meaning close together. So "experience training robot policies from
human demonstrations" lands next to a resume line about imitation learning,
although the two share no keywords.

1. The resume is split into its statements, such as each bullet and each skills
   line.
2. The posting is split into sentences, with boilerplate such as the equal
   opportunity notice and the benefits list removed.
3. Each posting sentence is paired with the closest resume statement. The score
   blends how strong the best dozen pairings are with how well the requirement
   sentences are covered on average.

Nothing is sent to any service. The page shows the mean of the keyword score
and the meaning score unless you pick one. A posting with too little text gets
no meaning score.

## Requirements read from the posting

A similarity score cannot read a number, so "5+ years" and "1 year" look alike
to it. `requirements.py` reads those details by pattern matching. It looks for
years of experience asked, degrees named, a minimum GPA, citizenship and
clearance rules, a statement that the employer will not sponsor a visa,
graduation years, and named credentials. These are facts about the posting. They
show as tags and drive the experience filter. Nothing about the reader is stored
or compared, and the patterns can miss or misread a requirement.

## Finding more employers

`data/candidates.json` holds tens of thousands of company career sites gathered
from public lists. Reading all of them on every run would be slow and would
lean on those sites for no reason, since most never post a internship. So
`survey.py` reads each candidate once in a while, and a site that has a
internship open at that moment is added to `data/companies.json`, which
is what the regular run reads. A scheduled job surveys one seventh of the
candidates each night, so every candidate is looked at once a week.

The candidate list was put together from the links in public internship and
new-graduate job boards and from two open datasets of career site addresses:
[kalil0321/ats-scrapers](https://github.com/kalil0321/ats-scrapers) (MIT) and
[datascry/openroles](https://github.com/datascry/openroles) (CC BY-SA 4.0).

## Running it yourself

It needs Python 3 and PyYAML, plus fastembed for the meaning score.

```bash
python3 collect.py                 # boards and career sites, about a minute
python3 collect.py --no-careers    # boards only, a few seconds
python3 collect.py --only simplify,openquant
python3 collect.py --describe 0    # skip reading descriptions

# build your own private profile, then see what postings ask for that it lacks
python3 match.py --build-profile General=cv.pdf Quant=quant.pdf
python3 match.py --gaps
```

The keyword profile lives in `private/profile.json` and the resume statements
for the meaning score in `private/statements.json`. Git ignores both. To score
in the scheduled run, store them as repository secrets named `RESUME_PROFILE`
and `RESUME_STATEMENTS`. Reading a PDF needs `pdftotext`, and the meaning score
needs `pip install fastembed`.

```bash
python3 semantic.py --build-statements General=cv.pdf Quant=quant.pdf
python3 semantic.py --rescore      # after a resume changes
```

| File | What it holds |
|---|---|
| `docs/list.json` | Every active listing, with the fields the page shows |
| `docs/data.json` | The same listings with every field |
| `data/semantic.json` | The meaning score of each posting |
| `docs/listings.csv` | The same list for a spreadsheet |
| `data/seen.json` | The day each listing was first seen |
| `data/companies.json` | The career sites to check |
| `data/history.json` | When each company first posted last summer |
| `data/manual.json` | Employers to check by hand, written by hand |
| `docs/timing.json` | What the "Not posted yet" tab shows |
| `docs/manual.json` | What the "Check by hand" tab shows |
| `data/terms.json` | The skills each posting mentions, read once and kept |
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

A skill is one line in `skills.py`. A board is one function in `collect.py` that returns listings in the common
shape, plus one line in `SOURCES`. A careers platform is one function in
`ats.py`, plus one line in `READERS` and a link pattern in `_PATTERNS`.
