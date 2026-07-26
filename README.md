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
| [`replx`](https://github.com/trycopilotai/replx) | A repair loop that does not assume exit 0 means success. Declares a success condition, refuses the repairs that make a command pass without fixing the defect, and ships a benchmark that scores the difference. |

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

`meta/` is the only file set a human edits by hand.
`catalogue.json` and `INDEX.md` are built from it by
`make catalogue`, and `make catalogue-check` fails when the
committed copies are stale.

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
    "ref": "v0.1.0"
  }
}
```

## Checks

```sh
make validate         # marketplace, plugin manifests, SKILL.md spec, vendor drift
make catalogue-check  # the generated index is current
make check            # both, which is what CI runs
```

`make validate` enforces the Agent Skills naming rules, the
1024-character description limit, the rule that a skill's
frontmatter `name` matches its directory, the 500-line
guideline for `SKILL.md`, and the requirement that any
remote plugin source is pinned to a `ref` or a `sha`.

## Adding a skill

See [CONTRIBUTING.md](CONTRIBUTING.md) for the bar a skill
has to clear before it is listed here.

## License

MIT for this repository. Each skill carries its own
`license` in its `meta/` entry and in its home repository.
