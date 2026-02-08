"""DSPy Signature definitions for each analysis task."""

from typing import Any

import dspy


class SecurityAudit(dspy.Signature):
    """You are an expert application security engineer.
    Analyze the provided source tree for security vulnerabilities,
    insecure coding patterns, hardcoded secrets, injection risks,
    broken auth flows, and misconfigurations.
    Provide severity ratings (critical / high / medium / low / info)
    and cite specific file paths and line-range references.

    Use the provided REPL tools to efficiently explore the codebase:
    grep_tree() to search for patterns, list_files() for file discovery,
    file_stats() for overview metrics, and llm_query() for sub-analysis."""
    source_tree: dict[str, Any] = dspy.InputField()
    analysis: str = dspy.OutputField(
        description="Detailed security audit in markdown with severity ratings."
    )


class ArchitectureReview(dspy.Signature):
    """You are a senior software architect.
    Analyze the codebase structure, identify design patterns, map module
    dependencies, evaluate separation of concerns, and flag architectural
    risks such as circular dependencies, god classes, or tight coupling.

    Use grep_tree() to trace imports and dependencies across files,
    list_files() to understand the project structure, and file_stats()
    for an overview of the codebase shape."""
    source_tree: dict[str, Any] = dspy.InputField()
    analysis: str = dspy.OutputField(
        description="Architecture review in markdown with dependency map and recommendations."
    )


class DocumentationGen(dspy.Signature):
    """You are a technical writer.
    Generate comprehensive developer documentation for the codebase:
    project overview, module descriptions, key APIs, data flows,
    setup instructions, and usage examples.
    Write for a new team member onboarding onto this project."""
    source_tree: dict[str, Any] = dspy.InputField()
    documentation: str = dspy.OutputField(
        description="Developer documentation in markdown."
    )


class CodeReview(dspy.Signature):
    """You are a senior engineer performing a thorough code review.
    Evaluate code quality, readability, test coverage gaps, error handling,
    performance concerns, and adherence to best practices.
    Prioritize actionable feedback with specific file and line references."""
    source_tree: dict[str, Any] = dspy.InputField()
    review: str = dspy.OutputField(
        description="Code review findings in markdown, ordered by priority."
    )


class DebugAnalysis(dspy.Signature):
    """You are an expert debugger.
    Given the source tree and a bug description, trace the likely root cause.
    Map the execution path, identify suspect code paths, and suggest fixes
    with specific file and line references.

    Use grep_tree() to find related patterns, and trace call chains
    across files using the REPL."""
    source_tree: dict[str, Any] = dspy.InputField()
    bug_description: str = dspy.InputField()
    analysis: str = dspy.OutputField(
        description="Root cause analysis in markdown with suggested fixes."
    )


class FreeformQuery(dspy.Signature):
    """You are a knowledgeable software engineer.
    Answer the given question about the codebase thoroughly, citing
    specific files and code when relevant."""
    source_tree: dict[str, Any] = dspy.InputField()
    question: str = dspy.InputField()
    answer: str = dspy.OutputField(
        description="Detailed answer in markdown with code references."
    )


class IncrementalRefresh(dspy.Signature):
    """You are a senior engineer updating a previous codebase analysis.
    Given the previous analysis baseline and the set of files that changed,
    determine what findings are affected, produce updated analysis for
    the changed areas, and note any new issues or resolved issues."""
    previous_analysis: str = dspy.InputField()
    changed_files: dict[str, Any] = dspy.InputField()
    task_type: str = dspy.InputField(
        description="The type of analysis to refresh: security, architecture, documentation, or review."
    )
    updated_analysis: str = dspy.OutputField(
        description="Updated analysis in markdown, noting what changed from the baseline."
    )


TASK_SIGNATURES = {
    "security": SecurityAudit,
    "architecture": ArchitectureReview,
    "documentation": DocumentationGen,
    "review": CodeReview,
}

TASK_OUTPUT_FIELD = {
    "security": "analysis",
    "architecture": "analysis",
    "documentation": "documentation",
    "review": "review",
}
