# skills

The trycopilot.ai skill marketplace. One command adds it,
one command installs any skill in it.

```sh
/plugin marketplace add trycopilotai/skills
/plugin install replx@trycopilotai
```

The marketplace name is `trycopilotai`, so skills are
installed as `<skill>@trycopilotai`. Update the catalogue
later with `/plugin marketplace update`.

## What is in it

See [INDEX.md](INDEX.md) for the generated table, or
[catalogue.json](catalogue.json) for the machine-readable
version.

| Skill                                            | What it does                                                                                                                                                                                                     |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`replx`](https://github.com/trycopilotai/replx) | Drive a failing build, test, lint, or health check to a success condition you declare, in bounded iterations. The condition can be stated in prose, so a goal the command does not measure is still a valid target, and the protocol refuses the repairs that make a command pass without fixing the defect. |

## Layout

```text
skills/
  .claude-plugin/marketplace.json   the catalogue Claude Code reads
  plugins/<name>/                   one directory per plugin
    .claude-plugin/plugin.json      the plugin manifest
    skills/<name>/SKILL.md          the skill itself
  meta/<name>.skill.yml             source of truth for the index
  catalogue.json                    generated, do not edit
  INDEX.md                          generated, do not edit
  tools/                            validation, index build, upstream sync
```

Three file sets are hand-edited: `meta/`,
`.claude-plugin/marketplace.json`, and each plugin's
`.claude-plugin/plugin.json`. `catalogue.json` and `INDEX.md`
are generated from `meta/` by `make catalogue`, and
`make catalogue-check` fails when the committed copies are
stale without rewriting them.

`meta/` and `marketplace.json` deliberately hold two copies of
each skill's name, licence, and description, because the
marketplace file is the one Claude Code reads directly.
`make validate` requires the copies to be identical, so the
duplication cannot drift.

Files under `tools/` carry a `.gpt` before the extension.
It records that the file was written by an AI agent rather
than typed by hand, which is a fact about provenance a reader
of a public repository is entitled to. It has one practical
cost: `test_guards.gpt.py` is not a valid Python module name,
so it is run directly rather than through
`unittest discover`.

## Vendoring and drift

Each skill has a home repository. `replx` lives at
[`trycopilotai/replx`](https://github.com/trycopilotai/replx),
which is where its examples, issues, and releases are.

This repository vendors a copy of each `SKILL.md` so the
marketplace resolves from a single clone. Every vendored
copy records the upstream ref and a `vendored_sha256` in its
`meta/` entry, and `make validate` fails if the file on disk
no longer matches. Refresh with `make sync`, which fetches
the pinned upstream tag and rewrites the recorded hashes.

The alternative is a `github` plugin source pointing
straight at the upstream repository, which removes the copy
entirely. That requires each upstream repo to carry its own
`.claude-plugin/plugin.json`. Once `replx` does, its entry
becomes:

```json
{
  "name": "replx",
  "source": {
    "source": "github",
    "repo": "trycopilotai/replx",
    "ref": "v0.2.0"
  }
}
```

## Checks

```sh
make validate         # marketplace, plugin manifests, SKILL.md spec, vendor drift
make catalogue-check  # the generated index is current
make test             # the tooling's own guards still fire
make check            # all three; CI runs them as separate steps
```

`make validate` enforces the Agent Skills naming rules, the
1024-character description limit, the rule that a skill's
frontmatter `name` matches its directory, the 500-line
guideline for `SKILL.md`, the requirement that any remote
plugin source is pinned to a `ref` or a `sha`, that every
`meta/` entry declares an explicit integer `order` and all
three side-effect flags, and that `meta/` agrees with
`marketplace.json`.

`make test` is the part worth explaining. It copies the
repository to a temporary directory, breaks it on purpose, and
checks that the tooling refuses: a `vendored_path` that
escapes the checkout, an upstream tag that has moved since it
was pinned, a plugin entry with no source, an unparseable
`plugin.json`, a missing side-effect flag. A guard with no
test is a comment.

## Adding a skill

See [CONTRIBUTING.md](CONTRIBUTING.md) for the bar a skill
has to clear before it is listed here.

## License

MIT for this repository. Each skill carries its own
`license` in its `meta/` entry and in its home repository, and
a vendored skill also carries that repository's `LICENSE` and
a `NOTICE` beside the copy.

## Not affiliated with GitHub

`trycopilot.ai` is an independent project. It is not
affiliated with, endorsed by, or connected to GitHub,
Microsoft, or GitHub Copilot. The name is a domain the author
owns and predates this repository.
