from __future__ import annotations

from typing import Callable, Optional

from trustgate.audit import AuditLog
from trustgate.broker.onepassword import OnePasswordClient
from trustgate.engine.policy import TTL, policy_for
from trustgate.engine.scorer import TrustScorer
from trustgate.models import (
    ActionRequest,
    CredentialHandle,
    Decision,
    Policy,
    TrustAssessment,
)

# An approver decides whether to release a credential in the APPROVE band.
# In the live demo this pings Slack or your phone; here it's just a callable.
Approver = Callable[[ActionRequest, TrustAssessment], bool]


class AccessBroker:
    """Scores each action, then decides what (if anything) 1Password releases.

    This is the heart of the system. The agent calls request_access(); it never
    touches the vault directly and never holds a long-lived key.
    """

    def __init__(
        self,
        scorer: TrustScorer,
        vault: Optional[OnePasswordClient] = None,
        audit: Optional[AuditLog] = None,
        approver: Optional[Approver] = None,
    ) -> None:
        self.scorer = scorer
        self.vault = vault or OnePasswordClient()
        self.audit = audit or AuditLog()
        self.approver = approver
        self.history: list[ActionRequest] = []

    def request_access(self, request: ActionRequest) -> Decision:
        assessment = self.scorer.assess(request, self.history)
        policy = policy_for(assessment.score)

        credential: Optional[CredentialHandle] = None
        reason = ""

        if policy is Policy.DENY:
            reason = "trust below threshold; credential withheld"

        elif policy is Policy.APPROVE:
            approved = self.approver(request, assessment) if self.approver else False
            if approved:
                credential = self._issue(request, policy)
                reason = "released after human approval"
            else:
                policy = Policy.DENY
                reason = "human approval not granted; credential withheld"

        else:  # ALLOW or NARROW
            credential = self._issue(request, policy)
            reason = f"released under {policy.value} policy"

        # Record the request in history *after* scoring so velocity reflects the past.
        self.history.append(request)

        decision = Decision(
            request=request,
            assessment=assessment,
            policy=policy,
            credential=credential,
            reason=reason,
        )
        self.audit.record(decision)
        return decision

    def _issue(self, request: ActionRequest, policy: Policy) -> CredentialHandle:
        # The raw secret is resolved here and would be used server-side to perform
        # the protected call. It is deliberately never attached to the handle or
        # the Decision, so it cannot leak back into the agent's context.
        _secret = self.vault.resolve(request.secret_ref)  # noqa: F841
        del _secret
        return CredentialHandle(
            secret_ref=request.secret_ref,
            ttl_seconds=TTL[policy],
            issued_for=request.action,
        )
