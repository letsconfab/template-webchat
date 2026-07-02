# Issue tracker: GitHub

Issues and PRDs for this repository live in GitHub Issues for
`letsconfab/template-webchat`. Use the `gh` CLI for all operations.

## Conventions

- Create: `gh issue create --title "..." --body "..."`
- Read: `gh issue view <number> --comments`
- List: `gh issue list --state open --json number,title,body,labels,comments`
- Comment: `gh issue comment <number> --body "..."`
- Apply or remove labels: `gh issue edit <number> --add-label "..."` or
  `gh issue edit <number> --remove-label "..."`
- Close: `gh issue close <number> --comment "..."`

Infer the repository from `git remote -v`; `gh` does this automatically inside
the clone.

## Pull requests as a triage surface

External pull requests are not treated as request submissions. Triage skills
process GitHub Issues only.

## Skill operations

When a skill says to publish to the issue tracker, create a GitHub issue. When a
skill says to fetch a ticket, run `gh issue view <number> --comments`.
