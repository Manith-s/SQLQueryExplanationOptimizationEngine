"""LLM prompting templates and helpers for SQL explanation."""

SYSTEM_PROMPT = "You are an expert PostgreSQL database engineer explaining SQL queries."


def explain_template(
    sql: str,
    ast=None,
    plan=None,
    warnings=None,
    metrics=None,
    audience="practitioner",
    style="concise",
    length="short",
    max_length=2000,
):
    """Generate a simple prompt for explaining a SQL query."""
    length_instruction = {
        "short": "in one sentence",
        "medium": "in a few sentences",
        "long": "in detail with comprehensive analysis",
    }.get(length, "in one sentence")

    style_instruction = {
        "concise": "concisely",
        "detailed": "with detailed explanations",
        "verbose": "thoroughly",
    }.get(style, "concisely")

    return f"Explain this SQL query {length_instruction} and {style_instruction} for a {audience}: {sql}"
