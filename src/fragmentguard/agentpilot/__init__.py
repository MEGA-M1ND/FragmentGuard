"""Agent-executed pilot: a small resource environment, an application-side action
recorder, sequential three-agent episodes, and an adapter into FragmentGuard.

Every resource effect is performed by the application (``workspace.Workspace``)
and recorded before the agent is told it succeeded. Normalized FragmentGuard
streams are derived from those records, never from an agent's own account.
All data is fictitious; the pilot scenarios are self-authored, not validated.
"""
