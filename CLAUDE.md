# CLAUDE.md

Guidance for working in this repository. An interactive lighting installation: a MIDI
keyboard lights individual laser beams, with chords triggering bonus effects. Two
builds — `qlcplus/` (PC + QLC+) and `standalone/` (Raspberry Pi + ArtNet).

For how the code works see `info.md` (auto-loaded below); for requirements, roadmap and
bugs see `reqs.md`; for the outward overview see `README.md`.

<!-- LLMbootstrap:module=core v=1 START — managed block, edit the source not here -->
## Project conventions (managed by LLMbootstrap)
- This project's workflow is defined by `LLMbootstrap.md`. The blocks between
  `<!-- LLMbootstrap:module=... -->` markers are compiled from it — edit the
  source and re-apply, never hand-edit a managed block.
- Do not modify or restructure `LLMbootstrap.md` as a side effect of routine work.
  Change it only when altering the workflow itself is the explicit task.
- Record only facts explicitly present in the project; don't fabricate. When
  something is implied but ambiguous, raise it as an open question.
<!-- LLMbootstrap:module=core END -->

<!-- LLMbootstrap:module=requirements v=4 START — managed block, edit the source not here -->
## Requirements & tracking
- Goals, requirements, bugs, todos are tracked in `reqs.md` (overview + source of
  truth for status/priority/severity/trace) and `reqs/<ID>.md` detail files.
- IDs are stable and never reused: `G#` goals, `R#` requirements
  (Type F=function / Q=quality / C=constraint), `B#` bugs. Todos are checklist lines.
- Requirements use "shall", are singular and verifiable, and each traces to a goal.
- `Done` means implemented and not known to be broken — verified by use, not
  necessarily by a test; a problem found later becomes a `B#` bug, not a reopened
  requirement. You may record already-built behavior (as-built) and mark it `Done`
  once the implementation is present in the code (the code is the evidence).
- An item's tracked status, priority, and severity live ONLY in the `reqs.md`
  tables — the `Done` flag there is authoritative. Detail files (headed
  `# <ID> — <name>`) hold description plus *working* checklists (acceptance
  criteria, fix steps); those checkboxes are progress notes, not the tracked status.
- Give an item its own `reqs/<ID>.md` file only when it needs detail (repro steps,
  acceptance criteria, design notes). Trivial items stay as table rows / checklist lines.
- On add/complete/fix: update `reqs.md`. Reference IDs in commits, e.g. `fix(B1): ...`.
<!-- LLMbootstrap:module=requirements END -->

<!-- LLMbootstrap:module=readme v=1 START — managed block, edit the source not here -->
## README
- `README.md` is the GitHub-facing technical document: what the project does
  (from the goals in `reqs.md`) and how to use it. Keep it factual, not marketing.
- When the goals (`G#`) or the way the project is run change, update `README.md`.
- Don't document commands, options, or behavior that don't exist.
<!-- LLMbootstrap:module=readme END -->

<!-- LLMbootstrap:module=workflow v=1 START — managed block, edit the source not here -->
## Working loop (reqs-first)
- Before making any change, reconcile it with `reqs.md` FIRST: if it fits the
  existing goals/requirements, proceed; if it is new, add the requirement / todo
  (or goal) first; if it changes one, edit that requirement first. Implement only
  after `reqs.md` reflects the intended change.
- Never work from memory. Goals, requirements, decisions, alignments, and tasks
  live in `reqs.md` / `reqs/`. If it isn't written there, it isn't decided — write
  it down rather than carrying it in your head.
- Keep `reqs.md` current as you go, so clearing the context or starting a new chat
  loses nothing. At the start of a session, read `reqs.md` to recover state before
  acting.
- If a request is ambiguous, out of scope, or conflicts with a goal, surface that
  against `reqs.md` and resolve it there before doing the work.
<!-- LLMbootstrap:module=workflow END -->

<!-- LLMbootstrap:module=docs v=1 START — managed block, edit the source not here -->
## Documentation
- Project documentation (how the code works, architecture, design, internal usage)
  lives in `info.md`, auto-loaded via the import below. Bulky reference material
  (API references, manuals, specs) lives under `docs/`, linked from `info.md`.
- Keep `CLAUDE.md` to rules and pointers — put documentation in `info.md` (or
  `docs/`), never inline here. Update `info.md` when the code's behavior or design
  changes.
@info.md
<!-- LLMbootstrap:module=docs END -->
