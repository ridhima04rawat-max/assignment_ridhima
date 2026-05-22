# Deep Research Agent — Evaluation Report

**Generated:** 2026-05-22 17:08:42 UTC  
**Harness:** `eval_harness.py`  
**Turns executed:** 7  
**Successful turns:** 7/7  
**Total wall time:** 86.2s  

## Executive Summary

| Metric | Value |
|--------|-------|
| Mean citation density (per 1k chars) | 1.58 |
| Mean grounding integrity score | 1.000 |
| Mean factual coverage (keyword cases) | 0.750 |
| Mean ingest→yield ratio | 0.298 |

## Performance Matrix

| Case | Category | Success | Time (s) | Factual | Citations | Density/1k | Grounding | Ingest chars | Yield chars | Ratio |
|------|----------|---------|----------|---------|-----------|------------||-----------|--------------|-------------|-------|
| temporal_2025_2026 | Factual / Temporal | yes | 9.6 | 0.500 | 2 | 1.59 | 1.000 | 8000 | 1259 | 0.157 |
| multi_hop_policy | Multi-hop | yes | 10.0 | 1.000 | 3 | 1.06 | 1.000 | 8000 | 2829 | 0.354 |
| comparison_ev_vs_h2 | Comparison | yes | 17.3 | 1.000 | 7 | 1.92 | 1.000 | 7999 | 3644 | 0.456 |
| conflicting_sources | Conflicting Sources | yes | 8.1 | 1.000 | 5 | 2.26 | 1.000 | 8000 | 2212 | 0.277 |
| insufficient_evidence | Insufficient Evidence | yes | 8.2 | 1.000 | 0 | 0.00 | 1.000 | 8000 | 755 | 0.094 |
| multi_turn_memory | Multi-turn Session | yes | 10.9 | 1.000 | 6 | 1.64 | 1.000 | 8000 | 3652 | 0.457 |
| multi_turn_memory_followup | Multi-turn Session | yes | 22.0 | 1.000 | 6 | 2.58 | 1.000 | 7959 | 2323 | 0.292 |

## Citation Integrity Breakdown

### `temporal_2025_2026`

- **Query:** What were the three largest technology sector corporate acquisitions announced in Q1 2026, and what were their publicly disclosed deal values in USD?
- **Citations detected:** 2
- **Citation density (per 1k chars):** 1.59
- **Grounding integrity score:** 1.000
- **Factual coverage score:** 0.500 (keywords: Hg Capital, OneStream, SpaceX, xAI)
- **Cited URLs:**
  - https://berkerynoyes.com/q1-2026-software-industry-trends
  - https://www.databahn.com/blogs/fortune-500-org-charts/major-billion-dollar-acquisitions-and-spin-offs-in-h1-2026
- **Grounding failures:** none
- **Planner queries:** largest tech acquisitions Q1 2026, Q1 2026 technology sector M&A deals, biggest tech company acquisitions January-March 2026
- **URLs opened:** 6

### `multi_hop_policy`

- **Query:** How did the EU AI Act enforcement timeline in 2025 affect open-source LLM deployment by European healthcare startups, and what compliance tooling emerged in response?
- **Citations detected:** 3
- **Citation density (per 1k chars):** 1.06
- **Grounding integrity score:** 1.000
- **Factual coverage score:** 1.000 (keywords: AI Act, Healthcare, Compliance, Startups)
- **Cited URLs:**
  - https://transcend.io/blog/eu-ai-act-implementation-timeline
- **Grounding failures:** none
- **Planner queries:** EU AI Act enforcement timeline 2025, open-source LLM deployment in European healthcare, EU AI Act compliance tooling for healthcare startups
- **URLs opened:** 6

### `comparison_ev_vs_h2`

- **Query:** Compare battery electric trucks versus hydrogen fuel-cell trucks for long-haul freight in 2025–2026 across cost, infrastructure readiness, and lifecycle emissions. Cite specific sources for each dimension.
- **Citations detected:** 7
- **Citation density (per 1k chars):** 1.92
- **Grounding integrity score:** 1.000
- **Cited URLs:**
  - https://www.here.com/learn/blog/hydrogen-vs-electric-trucking
  - https://www.intelligent-energy.com/news/fuel-cell-trucks-and-the-future-of-freight
- **Grounding failures:** none
- **Planner queries:** battery electric trucks vs hydrogen fuel cell trucks long haul freight 2025, cost comparison battery electric trucks hydrogen fuel cell trucks, lifecycle emissions battery electric trucks hydrogen fuel cell trucks 2026
- **URLs opened:** 6

### `conflicting_sources`

- **Query:** Is intermittent fasting more effective than caloric restriction for long-term weight maintenance according to recent clinical evidence?
- **Citations detected:** 5
- **Citation density (per 1k chars):** 2.26
- **Grounding integrity score:** 1.000
- **Cited URLs:**
  - https://pmc.ncbi.nlm.nih.gov/articles/PMC9099935
  - https://news.cuanschutz.edu/news-stories/intermittent-fasting-outperforms-calorie-counting-in-weight-loss-study
- **Grounding failures:** none
- **Planner queries:** intermittent fasting vs caloric restriction weight loss, clinical trials intermittent fasting long-term weight maintenance, recent studies comparing intermittent fasting and caloric restriction
- **URLs opened:** 6

### `insufficient_evidence`

- **Query:** What was the exact monthly active user count for the closed-beta social network 'NebulaThread' operating only in Antarctica as of March 2026?
- **Citations detected:** 0
- **Citation density (per 1k chars):** 0.00
- **Grounding integrity score:** 1.000
- **Cited URLs:** _(none detected)_
- **Grounding failures:** none
- **Planner queries:** NebulaThread Antarctica user count March 2026, NebulaThread closed beta monthly active users, Antarctica social network NebulaThread user base 2026
- **URLs opened:** 6

### `multi_turn_memory`

- **Query:** Summarize the current state of perovskite solar cell commercial deployment as of 2025–2026, naming specific companies and pilot projects.
- **Citations detected:** 6
- **Citation density (per 1k chars):** 1.64
- **Grounding integrity score:** 1.000
- **Cited URLs:**
  - https://exoswan.com/perovskite-stocks
  - https://www.renewable-ei.org/en/activities/reports/20251029.php
- **Grounding failures:** none
- **Planner queries:** perovskite solar cell commercial deployment 2025, companies investing in perovskite solar cells 2026, pilot projects perovskite solar energy 2025-2026
- **URLs opened:** 6

### `multi_turn_memory_followup`

- **Query:** Based on our earlier discussion in this session, which companies you mentioned are most likely to reach grid-scale deployment first, and why?
- **Citations detected:** 6
- **Citation density (per 1k chars):** 2.58
- **Grounding integrity score:** 1.000
- **Cited URLs:**
  - https://www.swiftsolar.com/news/partnering-with-eni-plenitude-to-unlock-us-utility-scale-perovskite-solar-deployment
  - https://www.perovskite-info.com/swift-solar
  - https://www.marketsandmarkets.com/ResearchInsight/perovskite-solar-cell-market.asp
  - https://www.renewable-ei.org/en/activities/reports/20251029.php
- **Grounding failures:** none
- **Planner queries:** perovskite solar cell companies grid scale deployment, companies leading in perovskite solar cell commercialization 2026, grid scale perovskite solar cell deployment timeline
- **URLs opened:** 6

## Factual Correctness

### `temporal_2025_2026`

- **Factual coverage:** 0.500
- **Expected anchors:** Hg Capital, OneStream, SpaceX, xAI
- **Missing keywords:** Hg Capital, OneStream

### `multi_hop_policy`

- **Factual coverage:** 1.000
- **Expected anchors:** AI Act, Healthcare, Compliance, Startups
- **Missing keywords:** none

## Calibration & Conflict Callouts

### Factual / Temporal (`temporal_2025_2026`)

_Requires recent 2025/2026 web evidence; tests recency of search, fetch, and citation of up-to-date sources._

- **Factual correctness:** ✅ Factual keyword coverage ≥ 50%.

### Multi-hop (`multi_hop_policy`)

_Forces the planner to issue multiple distinct search angles (policy, healthcare AI, compliance vendors)._

- **Factual correctness:** ✅ Factual keyword coverage ≥ 50%.

### Comparison (`comparison_ev_vs_h2`)

_Side-by-side comparison requiring multiple evidence strands and balanced citation across both technologies._

- **General:** No special calibration flags for this case.

### Conflicting Sources (`conflicting_sources`)

_Controversial topic where top results often disagree; tests explicit conflict callouts and dual-source citation._

- **Conflicting sources handling:** ✅ Conflict/discrepancy language present.

### Insufficient Evidence (`insufficient_evidence`)

_Obscure fictional/niche target with no authoritative public data; tests uncertainty calibration vs hallucination._

- **Uncertainty calibration:** ✅ Expressed uncertainty/language of doubt detected.

### Multi-turn Session (`multi_turn_memory`)

_Two sequential turns in one session_id; tests SQLite session memory and contextual follow-up answers._

- **Multi-turn memory:** ✅ Follow-up shows session-memory heuristic markers.

## Carbon / Efficiency Notes

_Efficiency proxy: characters ingested from ranked context chunks vs characters in the final answer (higher ratio = more compact synthesis)._

- `temporal_2025_2026`: ingested **8000** → yielded **1259** (ratio **0.157**, **9.6s**)
- `multi_hop_policy`: ingested **8000** → yielded **2829** (ratio **0.354**, **10.0s**)
- `comparison_ev_vs_h2`: ingested **7999** → yielded **3644** (ratio **0.456**, **17.3s**)
- `conflicting_sources`: ingested **8000** → yielded **2212** (ratio **0.277**, **8.1s**)
- `insufficient_evidence`: ingested **8000** → yielded **755** (ratio **0.094**, **8.2s**)
- `multi_turn_memory`: ingested **8000** → yielded **3652** (ratio **0.457**, **10.9s**)
- `multi_turn_memory_followup`: ingested **7959** → yielded **2323** (ratio **0.292**, **22.0s**)

## Answer Excerpts (first 400 chars)

### `temporal_2025_2026` — What were the three largest technology sector corporate acquisitions announced i…

## Largest Technology Sector Corporate Acquisitions in Q1 2026
The three largest technology sector corporate acquisitions announced in Q1 2026 are:

* SpaceX's acquisition of xAI for $250 billion ([Q1 2026 Software Industry Trends - Berkery, Noyes & Co., LLC.](https://berkerynoyes.com/q1-2026-software-industry-trends))
* Aligned Data Centers acquisition by AI Infrastructure Partnership / GIP / MGX for $40 billion+ ([Major Billion-Dollar+ Acquisitions and Spin-offs Closing in H1 2026 – Databahn](https://www.databahn.com/blogs/fortune-500-org-charts/major-billion-dollar-acquisitions-and-spin-offs-in-h1-2026))
* Meta Platforms' acquisition of Manus for approximately $2 billion is not among the top three, however, another large deal is IBM to acquire Confluent, but the deal value is not publicly disclosed in the provided sources.

However, it's essential to note that the provided sources do not contain enough information to conclusively answer the question about the third-largest technology sector corporate acquisition in Q1 2026. 

To reduce the uncertainty, the following search queries could be used:
1. "largest technology acquisitions Q1 2026"
2. "technology sector corporate acquisitions Q1 2026"
3. "biggest tech deals announced in Q1 2026"

**Plan excerpt:** 1. Search for Q1 2026 technology sector corporate acquisitions announcements.
2. Filter results to identify the three largest acquisitions.
3. Extract publicly disclosed deal values in USD for these acquisitions.

### `multi_hop_policy` — How did the EU AI Act enforcement timeline in 2025 affect open-source LLM deploy…

## EU AI Act Enforcement Timeline Impact on Open-Source LLM Deployment
The EU AI Act's implementation timeline, which stretches from 2024 to 2030, has significant implications for open-source Large Language Model (LLM) deployment by European healthcare startups ([The EU AI Act’s Implementation Timeline: Key Milestones for Enforcement | Transcend | The compliance layer for customer data](https://transcend.io/blog/eu-ai-act-implementation-timeline)). 

### Key Milestones
- The EU AI Act entered into force on August 1, 2024 ([The EU AI Act’s Implementation Timeline: Key Milestones for Enforcement | Transcend | The compliance layer for customer data](https://transcend.io/blog/eu-ai-act-implementation-timeline)).
- Starting in February 2025, the first provisions became mandatory for businesses, with additional key regulations to follow ([The roadmap to the EU AI Act: a detailed guide - Alexander Thamm [at]](https://www.alexanderthamm.com/en/blog/eu-ai-act-timeline)).
- The entire law will be applicable from August 1, 2026, except for certain high-risk AI systems ([The roadmap to the EU AI Act: a detailed guide - Alexander Thamm [at]](https://www.alexanderthamm.com/en/blog/eu-ai-act-timeline)).

### Compliance Tooling Emergence
In response to the EU AI Act, various compliance tooling has emerged to help businesses meet the requirements. For instance, Transcend offers tools for real-time data discovery and classification to simplify tracking and documenting data usage, ensuring compliance with the EU AI Act’s transparency requirements ([The EU AI Act’s Implementation Timeline: Key Milestones for Enforcement | Transcend | The compliance layer for customer data](https://transcend.io/blog/eu-ai-act-implementation-timeline)).

### Impact on European Healthcare Startups
While the retrieved evidence does not provide direct information on the impact of the EU AI Act enforcement timeline on open-source LLM deployment by European healthcare startups, it can be inferred that these s

_(truncated for report)_

**Plan excerpt:** 1. Identify key provisions of the EU AI Act related to open-source LLM deployment in healthcare.
2. Fetch reports and articles on the enforcement timeline in 2025 and its impact on European healthcare startups.
3. Analyze emerging compliance tooling and solutions developed in response to the EU AI Act.

### `comparison_ev_vs_h2` — Compare battery electric trucks versus hydrogen fuel-cell trucks for long-haul f…

## Comparison of Battery Electric Trucks and Hydrogen Fuel-Cell Trucks
### Introduction
The debate between battery electric trucks and hydrogen fuel-cell trucks for long-haul freight in 2025-2026 is ongoing. This comparison will examine the cost, infrastructure readiness, and lifecycle emissions of both options, citing specific sources for each dimension.

### Cost
According to [Future fuels: hydrogen versus electric batteries for next-gen trucks — www.here.com](https://www.here.com/learn/blog/hydrogen-vs-electric-trucking), hydrogen fuel cells are currently more expensive due to the complexity of production and the limited availability of hydrogen refueling stations. However, [Fuel Cell Trucks Shaping the Future of Freight — www.intelligent-energy.com](https://www.intelligent-energy.com/news/fuel-cell-trucks-and-the-future-of-freight) reports that hydrogen fuel cell trucks could reach cost parity with diesel in the UK by 2030, provided green hydrogen is priced around €5/kg.

### Infrastructure Readiness
The infrastructure for hydrogen fuel-cell trucks is currently limited, with fewer than 15 public hydrogen stations in the UK as of 2025, according to [Fuel Cell Trucks Shaping the Future of Freight — www.intelligent-energy.com](https://www.intelligent-energy.com/news/fuel-cell-trucks-and-the-future-of-freight). However, the H2Accelerate programme outlines plans for around 250 high-capacity stations along major freight routes by 2035 to support fleet-scale operations. In contrast, [Future fuels: hydrogen versus electric batteries for next-gen trucks — www.here.com](https://www.here.com/learn/blog/hydrogen-vs-electric-trucking) notes that the limited availability of charging infrastructure, particularly in remote or rural areas, is a significant challenge for electric trucks.

### Lifecycle Emissions
Both hydrogen fuel-cell trucks and battery electric trucks offer significant advantages over traditional fossil fuels in reducing harmful emissions. [Future fuels: hydrog

_(truncated for report)_

**Plan excerpt:** 1. Identify recent studies and reports from reputable sources such as the National Renewable Energy Laboratory, International Council on Clean Transportation, and industry publications that compare battery electric trucks and hydrogen fuel-cell trucks for long-haul freight.
2. Fetch data on cost, infrastructure readiness, and lifecycle emissions from these sources, including the US Department of Energy, European Alternative Fuels Observatory, and peer-reviewed journals.
3. Synthesize the informa

### `conflicting_sources` — Is intermittent fasting more effective than caloric restriction for long-term we…

## Answer to User Question
According to recent clinical evidence, intermittent fasting (IF) may be more effective than continuous calorie restriction (CCR) for weight loss, but the evidence is not conclusive for long-term weight maintenance. 

### Supporting Details
- A study found that IF was more effective than CCR for weight loss; however, there was no difference in BMI improvement ([Intermittent Fasting versus Continuous Calorie Restriction: Which Is Better for Weight Loss? - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9099935)).
- Another study suggested that IF might be superior to CCR because it helps conserve lean body mass at the expense of fat mass ([Intermittent Fasting versus Continuous Calorie Restriction: Which Is Better for Weight Loss? - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9099935)).
- A review of studies on IF and CCR found that IF decreased the levels of high-sensitivity C-reactive protein and prothrombin and thromboplastin times compared to CCR ([Intermittent Fasting versus Continuous Calorie Restriction: Which Is Better for Weight Loss? - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9099935)).
- A specific type of IF, 4:3 intermittent fasting, was found to outperform daily calorie restriction in a weight-loss study ([4:3 Intermittent Fasting Outperforms Daily Calorie Restriction in Weight-Loss Study](https://news.cuanschutz.edu/news-stories/intermittent-fasting-outperforms-calorie-counting-in-weight-loss-study)).

### Uncertainty and Gaps
There is uncertainty due to missing data on the long-term effectiveness of IF compared to CCR for weight maintenance. More research is needed to assess the mechanism of IF regimens and the safety of each type ([Intermittent Fasting versus Continuous Calorie Restriction: Which Is Better for Weight Loss? - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9099935)). 

### Next Search Queries
To reduce the gap in evidence, the following search queries could be used:
1. "long-term effects of intermittent fa

_(truncated for report)_

**Plan excerpt:** 1. Identify recent clinical trials comparing intermittent fasting and caloric restriction for weight loss.
2. Fetch studies published within the last 5 years from reputable databases such as PubMed and Google Scholar.
3. Synthesize findings, focusing on long-term weight maintenance outcomes and adverse effects.

### `insufficient_evidence` — What was the exact monthly active user count for the closed-beta social network …

## Answer
There is insufficient evidence to determine the exact monthly active user count for the closed-beta social network 'NebulaThread' operating only in Antarctica as of March 2026.

The provided sources do not mention 'NebulaThread' at all. They primarily discuss Facebook users in Antarctica and Threads statistics, but none of the sources provide information about 'NebulaThread' or its user count.

To find the answer, the following search queries could be useful:
- "NebulaThread user count March 2026"
- "NebulaThread monthly active users Antarctica"
- "Closed-beta social networks in Antarctica user statistics"

Without more specific information about 'NebulaThread', it is impossible to provide an accurate answer based on the given sources.

**Plan excerpt:** 1. Search for official press releases or statements from NebulaThread regarding their user base as of March 2026.
2. Investigate online archives and databases for any mentions of NebulaThread's user count, focusing on Antarctica-specific reports.
3. Analyze social media and online forums for any discussions or leaks about NebulaThread's active user count during the specified time frame.

### `multi_turn_memory` — Summarize the current state of perovskite solar cell commercial deployment as of…

## Current State of Perovskite Solar Cell Commercial Deployment
As of 2025-2026, the commercial deployment of perovskite solar cells is gaining momentum, with several companies making significant strides in the field. 

### Companies and Pilot Projects
Companies such as Tandem PV, Caelux, and CubicPV are at the forefront of perovskite solar cell development, with Tandem PV building a U.S. factory and targeting utility-scale customers in 2026 ([Top Perovskite Solar Stocks 2026: Shattering the Silicon Ceiling — exoswan.com](https://exoswan.com/perovskite-stocks)). Caelux has taken a shortcut by developing "Active Glass" that can replace the front glass of any existing silicon panel with perovskite-coated glass, creating an instant hybrid tandem, with its first commercial shipment in July 2025 ([Top Perovskite Solar Stocks 2026: Shattering the Silicon Ceiling — exoswan.com](https://exoswan.com/perovskite-stocks)). CubicPV has merged silicon wafer IP with perovskite R&D and hit a 24% mini-module record with NREL, and has a deal to supply next-gen cells to India's Waaree for a 2 GW production ([Top Perovskite Solar Stocks 2026: Shattering the Silicon Ceiling — exoswan.com](https://exoswan.com/perovskite-stocks)).

Other companies, such as UtmoLight and Microquanta Semiconductor, are also making progress, with UtmoLight launching a 1 GW production line in February 2025 and offering a 25-year power output guarantee, and Microquanta Semiconductor operating a 100 MW line and grid-connecting the world's largest perovskite solar farm at 8.6 MW ([Top Perovskite Solar Stocks 2026: Shattering the Silicon Ceiling — exoswan.com](https://exoswan.com/perovskite-stocks)).

### Cost Reduction and Deployment Expansion
The cost reduction of perovskite solar cells is being driven by new installation methods, with the Renewable Energy Institute publishing a report on perovskite solar cells to expand deployment sites, outlining trends in technological development to overcome cost and durabi

_(truncated for report)_

**Plan excerpt:** 1. Identify key industry reports and research articles on perovskite solar cell commercialization from 2025-2026.
2. Fetch company press releases and pilot project announcements from leading solar energy firms.
3. Synthesize information on current deployment trends, challenges, and future prospects.

### `multi_turn_memory_followup` — Based on our earlier discussion in this session, which companies you mentioned a…

## Current State of Perovskite Solar Cell Commercial Deployment
As of 2025-2026, the commercial deployment of perovskite solar cells is gaining momentum, with several companies making significant strides in the field. 

## Companies Likely to Reach Grid-Scale Deployment First
Based on the earlier discussion, Swift Solar is one of the companies most likely to reach grid-scale deployment first. This is due to its partnership with Eni Plenitude to unlock US utility-scale perovskite solar deployment ([Swift Solar — www.swiftsolar.com](https://www.swiftsolar.com/news/partnering-with-eni-plenitude-to-unlock-us-utility-scale-perovskite-solar-deployment)). The company has also acquired the core manufacturing assets and intellectual property of Meyer Burger, marking a step toward large-scale production of next-generation perovskite-silicon tandem solar cells in the United States ([Swift Solar - Company Profile and News — www.perovskite-info.com](https://www.perovskite-info.com/swift-solar)).

## Other Companies in the Perovskite Solar Cell Market
Other companies in the perovskite solar cell market include Hanwha Q CELLS (South Korea) and Microquanta Semiconductor (China), which are major players in the industry ([Top Perovskite Solar Cell Companies — www.marketsandmarkets.com](https://www.marketsandmarkets.com/ResearchInsight/perovskite-solar-cell-market.asp)).

## Challenges and Opportunities
Despite the challenges faced by perovskite solar cells, such as higher costs and shorter durability compared to conventional silicon-based products ([Perovskite Solar Cells to Expand Deployment Sites — www.renewable-ei.org](https://www.renewable-ei.org/en/activities/reports/20251029.php)), the market is projected to grow from USD 271 million in 2024 to USD 2,268 million by 2028, registering a CAGR of 70.1% during the forecast period ([Top Perovskite Solar Cell Companies — www.marketsandmarkets.com](https://www.marketsandmarkets.com/ResearchInsight/perovskite-solar-cell-market.asp)). Sw

_(truncated for report)_

**Plan excerpt:** 1. Review earlier conversation notes to identify companies mentioned in the context of perovskite solar cell commercial deployment. 
2. Fetch the latest news and press releases from these companies to assess their current progress and plans for grid-scale deployment. 
3. Compare the companies' technological advancements, funding, and partnerships to determine which are most likely to reach grid-scale deployment first.
