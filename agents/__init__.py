"""The three agents. Their prompts are the .md files in this folder; offline_agents.py is the
stand-in runner used until a model endpoint is approved (AGENTS.md section 8)."""


class AgentError(RuntimeError):
    """An agent could not do its job (a tool refused, or the reply was unusable)."""
