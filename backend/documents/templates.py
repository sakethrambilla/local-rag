"""Document templates defining section structure for BRD, SOW, PRD, and Custom documents."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TemplateSection:
    id: str                    # machine name (snake_case)
    title: str                 # display title
    section_type: str          # deliverable | timeline | requirement | acceptance_criterion | etc.
    obligation_language: str   # "shall" | "should" | "may"
    word_target: int
    prompt_hint: str           # additional LLM guidance for this section


@dataclass
class DocumentTemplate:
    doc_type: str
    title_format: str          # e.g., "Business Requirements Document — {topic}"
    sections: list[TemplateSection] = field(default_factory=list)


# ── BRD Template ──────────────────────────────────────────────────────────────

BRD_TEMPLATE = DocumentTemplate(
    doc_type="brd",
    title_format="Business Requirements Document — {topic}",
    sections=[
        TemplateSection(
            id="executive_summary",
            title="Executive Summary",
            section_type="executive_summary",
            obligation_language="should",
            word_target=300,
            prompt_hint=(
                "Provide a high-level overview of the project purpose, key stakeholders, "
                "and the business problem being solved. Keep it concise and non-technical."
            ),
        ),
        TemplateSection(
            id="business_objectives",
            title="Business Objectives",
            section_type="scope_statement",
            obligation_language="shall",
            word_target=250,
            prompt_hint=(
                "List specific, measurable business objectives. Use numbered list format. "
                "Each objective should be tied to a business outcome."
            ),
        ),
        TemplateSection(
            id="stakeholders",
            title="Stakeholders",
            section_type="background",
            obligation_language="may",
            word_target=200,
            prompt_hint=(
                "Identify key stakeholders (roles, not names), their interests, and "
                "their level of involvement (responsible/accountable/consulted/informed)."
            ),
        ),
        TemplateSection(
            id="scope",
            title="Scope",
            section_type="scope_statement",
            obligation_language="shall",
            word_target=300,
            prompt_hint=(
                "Define what is in scope and what is explicitly out of scope. "
                "Use two subsections: 'In Scope' and 'Out of Scope' with bullet lists."
            ),
        ),
        TemplateSection(
            id="functional_requirements",
            title="Functional Requirements",
            section_type="deliverable",
            obligation_language="shall",
            word_target=600,
            prompt_hint=(
                "List all functional requirements. Use the format: "
                "FR-001: [The system] shall [action]. Group by functional area if appropriate."
            ),
        ),
        TemplateSection(
            id="non_functional_requirements",
            title="Non-Functional Requirements",
            section_type="technical_constraint",
            obligation_language="shall",
            word_target=300,
            prompt_hint=(
                "Cover performance, security, scalability, availability, and compliance "
                "requirements. Use the format: NFR-001: [The system] shall [constraint]."
            ),
        ),
        TemplateSection(
            id="constraints",
            title="Constraints & Assumptions",
            section_type="assumption_risk",
            obligation_language="should",
            word_target=200,
            prompt_hint=(
                "List known technical, business, or regulatory constraints. "
                "Separately list key assumptions made in this document."
            ),
        ),
        TemplateSection(
            id="success_criteria",
            title="Success Criteria",
            section_type="acceptance_criterion",
            obligation_language="shall",
            word_target=200,
            prompt_hint=(
                "Define measurable criteria that will determine project success. "
                "Each criterion should be verifiable and tied to a business objective."
            ),
        ),
    ],
)

# ── SOW Template ──────────────────────────────────────────────────────────────

SOW_TEMPLATE = DocumentTemplate(
    doc_type="sow",
    title_format="Statement of Work — {topic}",
    sections=[
        TemplateSection(
            id="overview",
            title="Overview",
            section_type="executive_summary",
            obligation_language="should",
            word_target=250,
            prompt_hint=(
                "Describe the purpose of this engagement, parties involved, "
                "and the high-level objective of the work to be performed."
            ),
        ),
        TemplateSection(
            id="scope_of_work",
            title="Scope of Work",
            section_type="scope_statement",
            obligation_language="shall",
            word_target=400,
            prompt_hint=(
                "Detail the specific work, tasks, and activities the vendor shall perform. "
                "Be explicit about included and excluded activities."
            ),
        ),
        TemplateSection(
            id="deliverables",
            title="Deliverables",
            section_type="deliverable",
            obligation_language="shall",
            word_target=300,
            prompt_hint=(
                "List each deliverable with: name, description, format, and due date or milestone. "
                "Use a table or numbered list. Each deliverable must be tangible and measurable."
            ),
        ),
        TemplateSection(
            id="timeline",
            title="Timeline & Milestones",
            section_type="timeline",
            obligation_language="shall",
            word_target=300,
            prompt_hint=(
                "Provide a project timeline with key milestones and dates. "
                "Include start date, major phase dates, and completion date."
            ),
        ),
        TemplateSection(
            id="acceptance_criteria",
            title="Acceptance Criteria",
            section_type="acceptance_criterion",
            obligation_language="shall",
            word_target=250,
            prompt_hint=(
                "Define clear, testable acceptance criteria for each deliverable. "
                "Specify the review and sign-off process."
            ),
        ),
        TemplateSection(
            id="payment_terms",
            title="Payment Terms",
            section_type="financial",
            obligation_language="shall",
            word_target=200,
            prompt_hint=(
                "Describe the payment schedule, amounts, and conditions. "
                "Tie payments to milestone completion where applicable."
            ),
        ),
        TemplateSection(
            id="assumptions",
            title="Assumptions & Dependencies",
            section_type="assumption_risk",
            obligation_language="should",
            word_target=200,
            prompt_hint=(
                "List assumptions that the vendor is making about the client's environment, "
                "resources, and cooperation. Also list external dependencies."
            ),
        ),
    ],
)

# ── PRD Template ──────────────────────────────────────────────────────────────

PRD_TEMPLATE = DocumentTemplate(
    doc_type="prd",
    title_format="Product Requirements Document — {topic}",
    sections=[
        TemplateSection(
            id="overview",
            title="Overview",
            section_type="executive_summary",
            obligation_language="should",
            word_target=250,
            prompt_hint=(
                "Describe the product, its purpose, and the problem it solves. "
                "Include the target audience and key value proposition."
            ),
        ),
        TemplateSection(
            id="goals",
            title="Goals & Non-Goals",
            section_type="scope_statement",
            obligation_language="shall",
            word_target=200,
            prompt_hint=(
                "List product goals (what success looks like) and explicitly call out "
                "non-goals (what this product will NOT do in this release)."
            ),
        ),
        TemplateSection(
            id="user_stories",
            title="User Stories",
            section_type="deliverable",
            obligation_language="shall",
            word_target=400,
            prompt_hint=(
                "Write user stories in the format: "
                "'As a [user type], I want to [action] so that [benefit].' "
                "Group by user persona. Include acceptance criteria for each story."
            ),
        ),
        TemplateSection(
            id="functional_specs",
            title="Functional Specifications",
            section_type="deliverable",
            obligation_language="shall",
            word_target=500,
            prompt_hint=(
                "Describe functional requirements in detail. "
                "Cover all system behaviors, edge cases, and error handling. "
                "Reference user stories where applicable."
            ),
        ),
        TemplateSection(
            id="non_functional_specs",
            title="Non-Functional Specifications",
            section_type="technical_constraint",
            obligation_language="shall",
            word_target=250,
            prompt_hint=(
                "Cover performance targets, security requirements, scalability needs, "
                "and accessibility standards (WCAG 2.1 AA if applicable)."
            ),
        ),
        TemplateSection(
            id="out_of_scope",
            title="Out of Scope",
            section_type="scope_statement",
            obligation_language="may",
            word_target=150,
            prompt_hint=(
                "Explicitly list features, capabilities, or use cases that are "
                "out of scope for this product version."
            ),
        ),
        TemplateSection(
            id="timeline",
            title="Timeline & Milestones",
            section_type="timeline",
            obligation_language="should",
            word_target=200,
            prompt_hint=(
                "Provide release milestones, key engineering phases, "
                "and target launch date."
            ),
        ),
    ],
)

# ── Custom Template ───────────────────────────────────────────────────────────

CUSTOM_TEMPLATE = DocumentTemplate(
    doc_type="custom",
    title_format="Document — {topic}",
    sections=[
        TemplateSection(
            id="introduction",
            title="Introduction",
            section_type="executive_summary",
            obligation_language="should",
            word_target=250,
            prompt_hint=(
                "Provide context and purpose for this document. "
                "State the problem or opportunity being addressed."
            ),
        ),
        TemplateSection(
            id="key_findings",
            title="Key Findings",
            section_type="deliverable",
            obligation_language="should",
            word_target=400,
            prompt_hint=(
                "Summarize the most important findings, insights, or discoveries "
                "from the source materials. Use bullet points or numbered lists."
            ),
        ),
        TemplateSection(
            id="recommendations",
            title="Recommendations",
            section_type="deliverable",
            obligation_language="should",
            word_target=300,
            prompt_hint=(
                "Provide actionable recommendations based on the findings. "
                "Prioritize by impact or urgency. Include rationale for each."
            ),
        ),
        TemplateSection(
            id="appendix",
            title="Appendix",
            section_type="background",
            obligation_language="may",
            word_target=200,
            prompt_hint=(
                "Include any supporting details, reference materials, or supplementary "
                "information that supports the main document body."
            ),
        ),
    ],
)

# ── Template registry ─────────────────────────────────────────────────────────

_TEMPLATES: dict[str, DocumentTemplate] = {
    "brd": BRD_TEMPLATE,
    "sow": SOW_TEMPLATE,
    "prd": PRD_TEMPLATE,
    "custom": CUSTOM_TEMPLATE,
}


def get_template(doc_type: str) -> DocumentTemplate:
    """Return the DocumentTemplate for the given doc_type.

    Falls back to CUSTOM_TEMPLATE for unknown types.
    """
    return _TEMPLATES.get(doc_type.lower(), CUSTOM_TEMPLATE)
