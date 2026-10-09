# ALPR source discovery and acquisition audit

> Historical proposal/prompt pack. All six source-discovery phases and cross-phase review fixes are now implemented and committed locally; see [the shared implementation record](../../../../.agent/plans/source-discovery-v2-2026-10-05.md) and [current STATUS](../../../../STATUS.md). The instructions and observations below retain their original scope; live acceptance and delivery remain pending. Use the current handoff for subsequent work; implementation prompts below describe completed scope.

## Original October 5 proposal text

Analyzed October 5, 2026. This is an investigation and set of proposals, not an implementation.

## Scope and limits

Read the installed app's five ALPR research runs, dated September 18–October 2, 2026, using SQLite read-only transactions. Four completed; one failed. They contain 208 source clusters across runs and rounds, and 105 captured snapshots. These are counts of recorded run-specific sources, not 208 independent studies. The repository database did not contain matching ALPR v2 runs in the inspected set.

Compared persisted discovery, clustering, acquisition, Probe, selection, and analysis artifacts with current source and public scholarly/institutional sources. No paid research, provider credentials, live-database writes, or application replacement. Existing acquisition/Probe tests: 18 passed. This validates current handling rules, not live retrieval success.

## Concrete source losses

### A discovered study with an already-known PDF was lost

Run `daf3e186-eb9c-42ec-b9ec-d992334a5428`, claim “Automated License Plate Cameras reduce crime,” cluster `194a4481-0b89-506d-9031-fb6716c958b4`:

- Study: *License plate reader (LPR) police patrols in crime hot spots: an experimental evaluation in two adjacent jurisdictions*.
- Known URLs included `https://doi.org/10.1007/s11292-011-9133-9` and `https://voiceofsandiego.org/wp-content/uploads/2018/04/Lum-et-al-2.pdf`.
- The only recorded fetch attempt used the DOI. It succeeded at the transport/extraction boundary but captured a 209-character site-error message. The alternate PDF was not attempted for that cluster.
- A separate earlier run captured the PDF successfully, preserving 19,202 characters. The loss was therefore acquisition routing rather than an absence of discovery.

### A useful review was discovered repeatedly but never captured as full text

*Measuring the Cost-Effectiveness of New Technologies in Policing: The Case of Automatic License Plate Readers (ALPR)*, DOI `10.1007/s41887-025-00099-y`, appeared in multiple runs. Stored Springer/DOI captures contained the same 209-character error message. An independently located [Cambridge repository PDF](https://api.repository.cam.ac.uk/server/api/core/bitstreams/23e54cf0-e802-44d8-b3a3-8ee2d57b1600/content) provides 19 pages and matches the title, DOI, and authors. That repository URL was absent from recorded raw discovery results.

### An abstract page substituted for a paper

The discrimination runs captured *Surveillance Inequality: Race, Poverty, and the Geography of Automated License Plate Reader Deployment* through a RePEc/IDEAS page. Its captured 9,809 characters included bibliographic material and other citations; the source-selection Probe included unrelated economics citations. Separate OSF captures for this and another relevant paper contained only “OSF.” Obtaining the underlying paper would support substantially better assessment of methods and limitations.

Across the five runs, 14 captured snapshots contained the 209-character site-error text, and three contained only “OSF.” These historical captures do not establish that fresh current-source runs still admit those shells.

## What current code already fixes, and what remains

Current `agents/v2_acquisition.py` rejects shell-only captures at the Probe stage. Existing tests verify this. A proposal merely to reject those captures would duplicate implemented work.

The remaining acquisition gap is recovery: `_acquire_cluster` returns on the first nonempty response; Probe happens afterward. Known alternates are included in the acquired URL set before Probe succeeds. A failed Probe excludes the source rather than causing the same study's next full-text location to be tried. Full-text recovery should preserve failed snapshots and provenance while continuing bounded acquisition of the intended work.

Provider PDF URLs are retained as metadata but are not automatically incorporated into source-cluster URL candidates. URL preference favors DOI-bearing discovery items; it does not assess which copy is most likely to provide the full document.

## Genuine discovery misses

Neither of the following URLs appeared in recorded raw search results for these five runs:

- [NIJ CrimeSolutions ALPR evaluation profile](https://crimesolutions.ojp.gov/ratedprograms/license-plate-recognition-technology-crime-deterrent). It provides evaluation methods and references to controlled studies. The page is historical and explicitly no longer updated; use it as an entry into the evidence base, with separate searches for subsequent work.
- [University of Washington: Leaving the Door Wide Open](https://jsis.washington.edu/humanrights/2025/10/21/leaving-the-door-wide-open/). Its authors investigate ALPR sharing and usage through public records. It offers primary-document-based evidence about deployment and use, rather than proving racial or income discrimination. Its relevance would require assessment against each exact claim.

The app already found several important controlled ALPR studies. This audit does not support a blanket conclusion that its search cannot find serious research.

## Improvement options

| Option | Concrete change | Why investigate it |
| --- | --- | --- |
| Content-aware acquisition recovery | Try direct PDFs and verified repository copies after empty, error-only, or abstract-only captures; follow document download links. | Directly addresses observed losses of strong sources. |
| Expand from strong seed papers | Retrieve references, papers citing the seed, related work, and relevant authors' publications. | Adds literature relationships to the existing query-based rounds. [OpenAlex supports these neighborhoods](https://help.openalex.org/how-to/api-recipes/). |
| Specialist evidence catalogs | Route policing claims into CrimeSolutions, the Global Policing Database, and research institutions; adapt catalogs by topic. | [The policing evidence map](https://www.college.police.uk/research/policing-interventions-evidence-gap-map) provides organized access to controlled studies and reviews. Current ALPR arXiv results often concern generic crime models or recognition engineering. |
| Broader metadata retrieval, then selective acquisition | Experiment with 20–50 metadata results where supported, then rank directness, study relevance, and novel coverage before fetching. | Initial and adaptive requests currently use `limit=5`; SERP requests use page 1. This is a plausible recall bottleneck, not a measured counterfactual gain. |
| Provider-specific query construction | Use concise concept combinations, aliases such as ALPR/LPR/ANPR, and supported Boolean syntax; compare lexical and semantic searches. | Long broad scholarly queries returned many tangential results. The OpenAlex adapter supports semantic requests, but current orchestration does not set its default-false semantic flag. [OpenAlex documents semantic search](https://help.openalex.org/api/semantic-search/). |
| Institution and public-record exploration | Follow a university research group's publications, agency evaluation pages, municipal audit attachments, and public-record reports. | Offers a route to primary reports and data poorly represented in general top-ranked results. The missed UW report is an example. |
| Claim-aware document preview | Prioritize substantive methods/results passages relevant to the claim and exclude bibliography/recommended-content passages from previews. | Current Probe scoring rewards numbers, citation markers, and conclusion-like text without claim-aware relevance. Poor previews can mislead selection despite a useful source identity. |

## Recommended order and success criteria

First recover already-discovered full text. Then add seed-paper expansion and topic-specific evidence catalogs. Test deeper metadata retrieval and query variants against a small source set before increasing expensive acquisition.

Measure whether the app discovers and obtains full text for known relevant independent studies; how many high-value candidates are lost to access or shell captures; and whether specialist searches add independently useful sources. Record discoveries separately from successful full-document acquisition and from final evidence admission. Do not treat more URLs or more model calls as the success criterion.

## Current source anchors

- `agents/v2_acquisition.py`: acquisition loop around lines 151–181; first-response return around line 417; passage scoring around line 535.
- `agents/v2_discovery.py`: normalization around line 89; URL preference around line 531.
- `researchassistant/research/v2_orchestrator.py:1263` and `agents/v2_adaptive_search.py:1437`: five-result search requests.
- `providers/openalex.py`: selected metadata and semantic switch; landing-page preference around line 178.
- `providers/search.py:56`: semantic default is false.
