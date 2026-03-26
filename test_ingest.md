meeting notes from meeting with Tom Stanton on 2026-03-26, it has to do to add to

Collapse all
Transition to Reusable Gen BI Backbone: Albert, Tom, and Paul Danifo discussed the strategic shift from dashboard-centric delivery to a reusable Gen BI backbone, emphasizing the centrality of KPI as a service, the integration of deterministic and generative services, and the need to build new capabilities alongside existing systems without disruption.00:22
.
Strategic Vision and Rationale: Albert outlined the motivation for moving away from fragmented, dashboard-centric BI delivery toward a reusable Gen BI backbone, highlighting issues such as complexity, slow delivery, and governance challenges. The new model aims to centralize KPI logic, enable trusted analytics, and support scalable, AI-enabled experiences.

.
KPI as a Service Core: The team agreed that KPI as a service will be the foundational building block of the new architecture, providing deterministic, governed calculations that serve as the trusted context for further reasoning, insights, and agent interactions.

.
Parallel Development with Existing Systems: Albert emphasized the importance of building the new Gen BI backbone alongside the current estate, ensuring ongoing projects are not disrupted and advocating for an incremental approach starting with high-value slices and reusable assets.

.
Reusable Data and Service Layers: The discussion included the creation of dedicated, project-owned data layers and reusable service patterns, with the goal of supporting multiple endpoints, lightweight UIs, and agent-based consumption, while maintaining strong governance and traceability.

Presented by Albert Hupa
1
Presented by Albert Hupa
2
Presented by Albert Hupa
3
Presented by Albert Hupa
4
Presented by Albert Hupa
5

Ontology and Knowledge Graph Implementation: Albert, Tom, and Paul Danifo explored the role of ontology as a horizontal semantic layer connecting data, business logic, and agents, debating its implementation, growth strategy, and the practicalities of mapping business concepts for reasoning and interoperability.06:16
.
Ontology as Semantic Layer: Albert described ontology as a universal semantic layer that links company concepts, agents, and data, serving as a knowledge graph that supports both deterministic and causal reasoning. The ontology is intended to provide shared vocabulary, mappings, and context for services and agents.

.
Implementation Approaches: The team discussed various implementation options for the ontology layer, including mature triplet stores, graph databases, and cloud-native solutions, with flexibility to use relational databases like Postgres depending on scale and requirements.

.
Incremental Growth and Use Cases: Albert and Tom advocated for starting with simple, business-driven use cases and expanding the ontology iteratively, rather than attempting to build a comprehensive model upfront. This approach allows the ontology to evolve in tandem with service development.

.
Causal Frameworks and Reasoning: Tom explained the use of directional acyclic graphs and causal inference frameworks within the ontology, enabling the encoding of business logic, actions, and consequences for agent-based reasoning and decision support.

Presented by Albert Hupa
6
Presented by Albert Hupa
7

AI-Ready Data Layers and Semantic Evolution: Paul Danifo, Tom, and Albert discussed the requirements for AI-ready data layers, the evolution of semantic practices, and the practical steps needed to ensure data is accessible, well-governed, and suitable for agent-based analytics.27:06
.
Defining AI-Ready Data: The group clarified that AI-ready data layers are not a final, static state but a set of evolving data artifacts tailored to support services like KPI as a service, with a focus on deterministic extraction and clear, English-based naming conventions.

.
Semantic Layer Evolution: Paul emphasized that many components of AI readiness, such as improved metadata and naming, are extensions of best practices that should already be in place, with the main new addition being the context graph for richer semantic connections.

.
Balancing Project and Product Focus: The team debated the risks of project-owned data layers and stressed the importance of aligning data modeling with broader product or domain perspectives to avoid fragmentation and ensure scalability.

Presented by Albert Hupa
8
Governance and KPI Stewardship: Tom and Paul Danifo addressed the extension of governance practices from core data products to the calculation and stewardship of KPIs, advocating for clear ownership, taxonomy, and integration with existing governance structures.34:47
.
Extending Governance to KPIs: Tom proposed that governance should not stop at the data layer but must encompass the calculation and definition of KPIs, ensuring that business-relevant metrics are governed, traceable, and consistently defined.

.
KPI Steward Role: The discussion highlighted the need for a KPI steward—an individual responsible for the accuracy and governance of key metrics, analogous to a data steward but focused on business outcomes and end-user interaction.

.
Standardization and Enforcement: Paul argued for enforcing clear taxonomy, ownership, and glossary terms for all business concepts, making governance a prerequisite for consumption and ensuring that processes and tooling support both centralized and federated models.

Technology Decision-Making and Next Steps: Albert, Tom, and Paul Danifo agreed to initiate a collaborative technology decision log and prepare for follow-up sessions focused on concrete architectural choices, with plans to circulate starter questions and involve additional stakeholders as needed.43:49
.
Collaborative Decision Log: Albert volunteered to prepare a technology decision log document, inviting Tom and Paul to contribute and iterate on foundational technology choices for the Gen BI architecture.

.
Preparation for Future Sessions: The team agreed to exchange a list of starter questions to guide the next meeting, aiming to clarify foundational requirements and avoid wasted effort, with the possibility of involving additional participants such as Ipsita.

Organizational Change and Governance Structure: Tom and Tim discussed upcoming organizational changes at Mondelez, including the rollout of new structures and the decoupling of traditional machine learning from generative AI in governance, reflecting a shift toward more flexible and differentiated oversight.48:50
.
Decoupling Governance for AI Types: Tom reported that Mondelez plans to separate governance processes for traditional machine learning models and generative AI, a change he has advocated for to streamline analytical development and reduce unnecessary oversight.

.
Anticipated Organizational Shifts: The conversation noted that upcoming changes, such as the rollout of the 'poet' initiative and broader structural adjustments, may impact the direction and implementation of AI and analytics projects within the company.

Are these notes useful?


Follow-up tasks
.
Starter Questions for Next Session: Send a list of starter questions to Paul Danifo to help prepare for the next meeting and clarify the direction for the architecture discussion. (Albert)
.
Technology Decision Log Preparation: Prepare a decision log document for technology choices and start working on it collaboratively with Tom and Paul Danifo, itera