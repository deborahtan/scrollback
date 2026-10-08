# Scrollback architecture (summary)

The full, living version is the [Scrollback architecture doc](https://claude.ai/code/artifact/cb01f59f-52ad-49fb-afb3-ca8ecf6ea70a).

## Three parts

1. **Stocking the library (on sync).** Collectors pull the last month of saves from TikTok
   (export file), Pinterest (API) and Drive (shared folder). Each save is snapshotted, then the
   Extractor writes a typed catalogue card. Runs once per save.
2. **Answering you (on a prompt).** You type naturally; the Intent Router turns it into
   editable filter chips, with a "Did you mean" row when unsure. The Retriever shortlists, the
   Curator picks 3 with a gather list, code checks and the Critic verify, and you get one card.
3. **Checking its own work (weekly).** The Auditor runs the golden set and posts a scorecard.

## Agent roster

| Agent | Job | Writes |
| --- | --- | --- |
| Collectors | Pull and snapshot saves | raw_saves |
| Extractor | Snapshot to item card | items (after schema check) |
| Librarian | Dedupe, mark source_gone, re-embed | items metadata |
| Intent Router | Prompt to intent + filter chips | nothing |
| Context Keeper | set_preference to a preferences patch | preferences (yours apply with Undo) |
| Tamaki Scout | Weather, events, places | context snapshot |
| Retriever | Hybrid search and rerank | nothing |
| Curator | The single decision-maker; cites item IDs | draft result |
| Critic | Taste and feasibility, one revision | nothing |
| Concierge | Result card, feedback taps | feedback |
| Auditor | Golden set, judge, scorecard | eval tables |

## Phase plan

1. Catalogue (this commit)
2. First intents: dinner and outfit
3. Prompt-to-filters app and preferences
4. Quality loop: Critic, Auditor, tracing
5. Tamaki layer and learning
