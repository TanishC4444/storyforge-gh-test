# Creative pipeline audit

The previous live run did not demonstrate adequate editorial judgment: the reviewer returned bare approvals, the editor changed very little, and scenes repeated discoveries. This update changes the contracts and information reaching each role. It does not establish that the model now writes good fiction. No live story generation was restarted for this audit.

## Creative input coverage

The complete test brief is `examples/silent-bell-deep.json`.

| Category | Input and use |
|---|---|
| Medium and length | Book or short story; chapters, scenes per chapter, scene word target and strict/guidance policy. The current hosted test graph has three chapters of three scenes. |
| Themes, tensions, conflicts | Weighted, typed keywords drive separate retrieval facets and remain in creative controls. |
| Scene design | Location, setting and dramatic function; each scene is reconciled against accepted events before character proposals. |
| World | Technology, institutions, physical systems, deadlines and constraints support causality review. |
| Characters | Goals, values, fears, strategies, limits, contradictions, emotional behavior, voice examples and arcs with pressure tests and costly choices. Other characters' private profiles are withheld from the writer's viewpoint packet. |
| Plot and subplots | Central question, causal dependencies, alternatives and costs; subplots have owners, intersections and removal costs. |
| Genre, tone, mood | Retained as creative controls rather than inferred solely from the premise. |
| References | Corpus IDs, application purpose, scope, target and exclusions. References can apply to the whole story, one chapter or one scene. |
| Adaptability | Strength, mode and maximum active sources. Strength is editorial guidance, not a measured percentage of influence. |
| Figurative language | Density, devices and image domains; rhetoric review checks specificity and coherence against this brief. |

The dummy makes the bell's operating mechanism, certification process, deadlines and alternative safety measures explicit. Mara, Oren and Ilya have competing commitments and different pressure behaviors. The second scene must change the problem rather than discover the first scene's evidence again. These are test requirements, not generated literary accomplishments.

## Revision and acceptance

Initial refinement → independent design critique → bounded revision if needed → fresh assessment. The outline follows the same sequence. A failed final assessment stops generation. Development review covers all twelve declared design categories and points to actual document fields.

Each scene then receives a fresh design reconciliation, parallel character proposals, direction, drafting and distinct-writing revision. Story review, rhetoric review and memory extraction operate in parallel. Story and rhetoric diagnoses feed one bounded repair; changed prose is checked again and memory refreshed. Memory has a separate verification gate. Only acceptance advances canon, and chapter boundaries have another review.

Story checks cover scene change, agency, depth, alternatives, dialogue tactics, continuity, viewpoint knowledge, subplots and reference application. Rhetoric checks cover redundant explanation, viewpoint specificity, emotional labeling, figurative coherence, gestures, rhythm and instruction leakage. Reviews require reasons and source paragraph IDs; failed checks require actionable issues. A bare `pass: true` with an empty issues array is insufficient. Core checks cannot be skipped as not applicable. Source anchoring establishes where evidence came from, not whether a model's interpretation is correct.

Only an explicit instruction-leak pattern has a deterministic prose blocker. Other stylistic signals are advisory: intentional repetition, plain statements, lyricism and genre choices remain valid. The editor may rebuild paragraphs within established event boundaries; larger causal problems go to structural repair.

These are automated checkpoints, not human approvals. Fresh runners remain inside one workflow, with sequential accepted state and parallel independent branches. The older compatibility CLI is not this full editorial pipeline.

## Actual RAG behavior

The earlier live run used keyword retrieval and selected Old Sultan, Fitcher's Bird and Bluebeard. That was real retrieval, but its integration into later writing was incomplete.

The current database has 605 analysis records, 603 eligible for retrieval, 605 rebuilt vectors and zero stale projections. The encoder revision and chunk pooling are pinned. Hybrid mode combines local semantic retrieval with keyword search and controlled mechanism matching across thematic, relationship and craft queries. Explicit valid reference IDs are selected separately and visibly labeled. Unknown or disabled references fail validation.

`examples/rag-output-deep.json` is an actual hybrid result, not a fixture. It contains source IDs and titles, mechanisms, analyses, themes, techniques, application guidance, limitations, retrieval hit provenance and requested scopes. `examples/rag-writer-packet.json` shows the smaller scene-specific writer input. Craft guide sections are selected by role; the rhetoric editor receives different sections from the architect. Zero adaptation strength excludes literary references while preserving craft guidance.

The deep brief explicitly requests Antigone, the Iliad and Old Sultan. Their presence therefore does not prove semantic search found them unaided. Separate unpinned development probes found Antigone for conflicting duties, Old Sultan for conflicting rescue debts and Fitcher's Bird for evidence-led rescue among their top three. These three handpicked probes informed ranking changes; they are not an independent benchmark. See `examples/rag-audit.json`.

For Antigone the application guidance asks for intelligible opposing obligations, a possible compromise and choices that make it unavailable. The output supplies narrative reasoning rather than classic source prose. A scoped application packet tells the writer what may transfer and what must not be borrowed. `reference-usage.json` records proposed applications and model assessments, not proof of originality or successful influence.

## Verification and remaining limits

All 33 automated tests passed. A separate nine-scene fixture run also passed using the deep brief and real hybrid retrieval. Automated tests exercise nine fixture scenes, parallel isolated branches, state acceptance, evidence binding, invalid approvals, design coverage, creative controls and scoped references. Fixtures verify contracts and orchestration; they cannot demonstrate literary improvement. The new review contracts have not been evaluated in a new live model run.

Retrieval quality needs a larger held-out query set. Corpus analyses remain drafts with recorded limitations. Models can still give bad reasons, overlook contradictions or approve weak prose. Working memory still selects within context budgets and can miss older facts. Arbitrary-length book orchestration, dependency-aware rewrites of earlier chapters and unrestricted world simulation are not implemented by this three-chapter test graph.
