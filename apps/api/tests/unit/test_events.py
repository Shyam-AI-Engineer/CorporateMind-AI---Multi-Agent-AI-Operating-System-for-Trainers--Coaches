"""Unit tests for all */events.py domain event dataclasses.

All domain events are frozen dataclasses with:
- Required typed fields
- occurred_at: datetime with a UTC default factory

Tests verify per event class:
- Instantiation with required fields
- Field values round-trip correctly
- occurred_at is a timezone-aware datetime by default
- Frozen semantics: attribute assignment raises AttributeError
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _assert_utc_datetime(instance) -> None:
    assert isinstance(instance.occurred_at, datetime)
    assert instance.occurred_at.tzinfo is not None


def _assert_frozen(instance) -> None:
    with pytest.raises(AttributeError):
        instance.occurred_at = datetime.now(UTC)


# ── Identity ───────────────────────────────────────────────────────────────────

class TestIdentityEvents:
    def test_user_registered_fields(self):
        from corpmind.modules.identity.events import UserRegistered
        evt = UserRegistered(user_id=_uuid(), org_id=_uuid(), email="trainer@example.com")
        assert evt.email == "trainer@example.com"
        assert isinstance(evt.user_id, uuid.UUID)
        _assert_utc_datetime(evt)

    def test_user_registered_is_frozen(self):
        from corpmind.modules.identity.events import UserRegistered
        _assert_frozen(UserRegistered(user_id=_uuid(), org_id=_uuid(), email="a@b.com"))

    def test_user_logged_in_fields(self):
        from corpmind.modules.identity.events import UserLoggedIn
        user_id = _uuid()
        evt = UserLoggedIn(user_id=user_id, org_id=_uuid())
        assert evt.user_id == user_id
        _assert_utc_datetime(evt)

    def test_plan_upgraded_tier_transition(self):
        from corpmind.modules.identity.events import PlanUpgraded
        evt = PlanUpgraded(org_id=_uuid(), from_tier="starter", to_tier="growth")
        assert evt.from_tier == "starter"
        assert evt.to_tier == "growth"
        _assert_utc_datetime(evt)

    def test_plan_upgraded_is_frozen(self):
        from corpmind.modules.identity.events import PlanUpgraded
        _assert_frozen(PlanUpgraded(org_id=_uuid(), from_tier="starter", to_tier="growth"))


# ── Campaigns ─────────────────────────────────────────────────────────────────

class TestCampaignEvents:
    def test_campaign_created_fields(self):
        from corpmind.modules.campaigns.events import CampaignCreated
        cid = _uuid()
        evt = CampaignCreated(campaign_id=cid, tenant_id=_uuid(), channel="email")
        assert evt.campaign_id == cid
        assert evt.channel == "email"
        _assert_utc_datetime(evt)

    def test_campaign_launched_recipient_count(self):
        from corpmind.modules.campaigns.events import CampaignLaunched
        evt = CampaignLaunched(campaign_id=_uuid(), tenant_id=_uuid(), recipient_count=250)
        assert evt.recipient_count == 250
        _assert_utc_datetime(evt)

    def test_campaign_paused_reason(self):
        from corpmind.modules.campaigns.events import CampaignPaused
        evt = CampaignPaused(
            campaign_id=_uuid(), tenant_id=_uuid(), reason="budget_exceeded"
        )
        assert evt.reason == "budget_exceeded"
        _assert_utc_datetime(evt)

    def test_campaign_rejected_by_compliance(self):
        from corpmind.modules.campaigns.events import CampaignRejected
        evt = CampaignRejected(
            campaign_id=_uuid(), tenant_id=_uuid(), rejected_by="compliance"
        )
        assert evt.rejected_by == "compliance"

    def test_campaign_rejected_by_hitl(self):
        from corpmind.modules.campaigns.events import CampaignRejected
        evt = CampaignRejected(
            campaign_id=_uuid(), tenant_id=_uuid(), rejected_by="hitl"
        )
        assert evt.rejected_by == "hitl"
        _assert_utc_datetime(evt)

    def test_campaign_created_is_frozen(self):
        from corpmind.modules.campaigns.events import CampaignCreated
        _assert_frozen(CampaignCreated(campaign_id=_uuid(), tenant_id=_uuid(), channel="email"))


# ── Compliance ────────────────────────────────────────────────────────────────

class TestComplianceEvents:
    def test_compliance_blocked_fields(self):
        from corpmind.modules.compliance.events import ComplianceBlocked
        evt = ComplianceBlocked(
            tenant_id=_uuid(), contact_id=_uuid(),
            channel="email", reason="unsubscribed",
        )
        assert evt.channel == "email"
        assert evt.reason == "unsubscribed"
        _assert_utc_datetime(evt)

    def test_compliance_blocked_is_frozen(self):
        from corpmind.modules.compliance.events import ComplianceBlocked
        _assert_frozen(
            ComplianceBlocked(
                tenant_id=_uuid(), contact_id=_uuid(), channel="email", reason="opt_in_missing"
            )
        )

    def test_unsubscribe_recorded_channel_none(self):
        from corpmind.modules.compliance.events import UnsubscribeRecorded
        evt = UnsubscribeRecorded(tenant_id=_uuid(), contact_hash="abc123", channel=None)
        assert evt.contact_hash == "abc123"
        assert evt.channel is None
        _assert_utc_datetime(evt)

    def test_unsubscribe_recorded_with_channel(self):
        from corpmind.modules.compliance.events import UnsubscribeRecorded
        evt = UnsubscribeRecorded(tenant_id=_uuid(), contact_hash="def456", channel="whatsapp")
        assert evt.channel == "whatsapp"


# ── Outreach ──────────────────────────────────────────────────────────────────

class TestOutreachEvents:
    def test_message_sent_fields(self):
        from corpmind.modules.outreach.events import MessageSent
        mid = _uuid()
        evt = MessageSent(message_id=mid, tenant_id=_uuid(), channel="email")
        assert evt.message_id == mid
        assert evt.channel == "email"
        _assert_utc_datetime(evt)

    def test_message_sent_is_frozen(self):
        from corpmind.modules.outreach.events import MessageSent
        _assert_frozen(MessageSent(message_id=_uuid(), tenant_id=_uuid(), channel="email"))

    def test_message_bounced_hard(self):
        from corpmind.modules.outreach.events import MessageBounced
        evt = MessageBounced(
            message_id=_uuid(), tenant_id=_uuid(),
            channel="email", bounce_type="hard",
        )
        assert evt.bounce_type == "hard"
        _assert_utc_datetime(evt)

    def test_message_bounced_soft(self):
        from corpmind.modules.outreach.events import MessageBounced
        evt = MessageBounced(
            message_id=_uuid(), tenant_id=_uuid(),
            channel="email", bounce_type="soft",
        )
        assert evt.bounce_type == "soft"

    def test_message_bounced_spam_complaint(self):
        from corpmind.modules.outreach.events import MessageBounced
        evt = MessageBounced(
            message_id=_uuid(), tenant_id=_uuid(),
            channel="email", bounce_type="spam_complaint",
        )
        assert evt.bounce_type == "spam_complaint"

    def test_reply_received_hash_stored(self):
        from corpmind.modules.outreach.events import ReplyReceived
        evt = ReplyReceived(
            message_id=_uuid(), tenant_id=_uuid(),
            channel="email", raw_reply_hash="sha256:abcdef",
        )
        assert evt.raw_reply_hash == "sha256:abcdef"
        _assert_utc_datetime(evt)


# ── Trainer Intel ─────────────────────────────────────────────────────────────

class TestTrainerIntelEvents:
    def test_trainer_profile_extracted_fields(self):
        from corpmind.modules.trainer_intel.events import TrainerProfileExtracted
        pid = _uuid()
        evt = TrainerProfileExtracted(
            profile_id=pid, tenant_id=_uuid(), workspace_id=_uuid()
        )
        assert evt.profile_id == pid
        assert isinstance(evt.workspace_id, uuid.UUID)
        _assert_utc_datetime(evt)

    def test_trainer_profile_extracted_is_frozen(self):
        from corpmind.modules.trainer_intel.events import TrainerProfileExtracted
        _assert_frozen(
            TrainerProfileExtracted(profile_id=_uuid(), tenant_id=_uuid(), workspace_id=_uuid())
        )

    def test_trainer_profile_locked_fields(self):
        from corpmind.modules.trainer_intel.events import TrainerProfileLocked
        pid = _uuid()
        evt = TrainerProfileLocked(profile_id=pid, tenant_id=_uuid())
        assert evt.profile_id == pid
        _assert_utc_datetime(evt)


# ── HR Discovery ──────────────────────────────────────────────────────────────

class TestHRDiscoveryEvents:
    def test_contacts_discovered_fields(self):
        from corpmind.modules.hr_discovery.events import ContactsDiscovered
        evt = ContactsDiscovered(tenant_id=_uuid(), count=42, source_type="company_website")
        assert evt.count == 42
        assert evt.source_type == "company_website"
        _assert_utc_datetime(evt)

    def test_contacts_discovered_is_frozen(self):
        from corpmind.modules.hr_discovery.events import ContactsDiscovered
        _assert_frozen(ContactsDiscovered(tenant_id=_uuid(), count=1, source_type="webinar"))

    def test_contact_marked_non_deliverable_hard_bounce(self):
        from corpmind.modules.hr_discovery.events import ContactMarkedNonDeliverable
        evt = ContactMarkedNonDeliverable(
            tenant_id=_uuid(), contact_id=_uuid(),
            channel="email", reason="hard_bounce",
        )
        assert evt.reason == "hard_bounce"
        assert evt.channel == "email"
        _assert_utc_datetime(evt)

    def test_contact_marked_non_deliverable_spam_complaint(self):
        from corpmind.modules.hr_discovery.events import ContactMarkedNonDeliverable
        evt = ContactMarkedNonDeliverable(
            tenant_id=_uuid(), contact_id=_uuid(),
            channel="whatsapp", reason="spam_complaint",
        )
        assert evt.reason == "spam_complaint"


# ── Social ────────────────────────────────────────────────────────────────────

class TestSocialEvents:
    def test_social_post_published_fields(self):
        from corpmind.modules.social.events import SocialPostPublished
        pid = _uuid()
        evt = SocialPostPublished(post_id=pid, tenant_id=_uuid(), channel="linkedin")
        assert evt.post_id == pid
        assert evt.channel == "linkedin"
        _assert_utc_datetime(evt)

    def test_social_post_published_is_frozen(self):
        from corpmind.modules.social.events import SocialPostPublished
        _assert_frozen(SocialPostPublished(post_id=_uuid(), tenant_id=_uuid(), channel="telegram"))

    def test_social_post_published_channels(self):
        from corpmind.modules.social.events import SocialPostPublished
        for channel in ("linkedin", "instagram", "facebook", "telegram"):
            evt = SocialPostPublished(post_id=_uuid(), tenant_id=_uuid(), channel=channel)
            assert evt.channel == channel


# ── WhatsApp ──────────────────────────────────────────────────────────────────

class TestWhatsAppEvents:
    def test_window_opened_stores_expiry(self):
        from corpmind.modules.whatsapp.events import WhatsAppWindowOpened
        expiry = datetime.now(UTC)
        evt = WhatsAppWindowOpened(
            tenant_id=_uuid(), contact_id=_uuid(), expires_at=expiry
        )
        assert evt.expires_at == expiry
        _assert_utc_datetime(evt)

    def test_window_opened_is_frozen(self):
        from corpmind.modules.whatsapp.events import WhatsAppWindowOpened
        _assert_frozen(
            WhatsAppWindowOpened(
                tenant_id=_uuid(), contact_id=_uuid(), expires_at=datetime.now(UTC)
            )
        )

    def test_template_rejected_reason(self):
        from corpmind.modules.whatsapp.events import WhatsAppTemplateRejected
        evt = WhatsAppTemplateRejected(
            tenant_id=_uuid(), template_id=_uuid(), reason="policy_violation"
        )
        assert evt.reason == "policy_violation"
        _assert_utc_datetime(evt)

    def test_template_rejected_is_frozen(self):
        from corpmind.modules.whatsapp.events import WhatsAppTemplateRejected
        _assert_frozen(
            WhatsAppTemplateRejected(tenant_id=_uuid(), template_id=_uuid(), reason="spam")
        )


# ── Proposals ─────────────────────────────────────────────────────────────────

class TestProposalsEvents:
    def test_proposal_generated_fields(self):
        from corpmind.modules.proposals.events import ProposalGenerated
        pid = _uuid()
        evt = ProposalGenerated(proposal_id=pid, tenant_id=_uuid(), contact_id=_uuid())
        assert evt.proposal_id == pid
        assert isinstance(evt.contact_id, uuid.UUID)
        _assert_utc_datetime(evt)

    def test_proposal_generated_is_frozen(self):
        from corpmind.modules.proposals.events import ProposalGenerated
        _assert_frozen(
            ProposalGenerated(proposal_id=_uuid(), tenant_id=_uuid(), contact_id=_uuid())
        )

    def test_proposal_sent_fields(self):
        from corpmind.modules.proposals.events import ProposalSent
        pid = _uuid()
        evt = ProposalSent(proposal_id=pid, tenant_id=_uuid())
        assert evt.proposal_id == pid
        _assert_utc_datetime(evt)


# ── CRM ───────────────────────────────────────────────────────────────────────

class TestCRMEvents:
    def test_lead_stage_changed_transition(self):
        from corpmind.modules.crm.events import LeadStageChanged
        evt = LeadStageChanged(
            lead_id=_uuid(), tenant_id=_uuid(),
            from_stage="discovered", to_stage="engaged",
        )
        assert evt.from_stage == "discovered"
        assert evt.to_stage == "engaged"
        _assert_utc_datetime(evt)

    def test_lead_stage_changed_is_frozen(self):
        from corpmind.modules.crm.events import LeadStageChanged
        _assert_frozen(
            LeadStageChanged(
                lead_id=_uuid(), tenant_id=_uuid(),
                from_stage="engaged", to_stage="meeting",
            )
        )

    def test_meeting_booked_fields(self):
        from corpmind.modules.crm.events import MeetingBooked
        lid = _uuid()
        evt = MeetingBooked(lead_id=lid, tenant_id=_uuid(), contact_id=_uuid())
        assert evt.lead_id == lid
        assert isinstance(evt.contact_id, uuid.UUID)
        _assert_utc_datetime(evt)


# ── Analytics ─────────────────────────────────────────────────────────────────

class TestAnalyticsEvents:
    def test_daily_rollup_computed_stores_date(self):
        from corpmind.modules.analytics.events import DailyRollupComputed
        today = date.today()
        evt = DailyRollupComputed(tenant_id=_uuid(), rollup_date=today)
        assert evt.rollup_date == today
        assert isinstance(evt.rollup_date, date)
        _assert_utc_datetime(evt)

    def test_daily_rollup_is_frozen(self):
        from corpmind.modules.analytics.events import DailyRollupComputed
        _assert_frozen(DailyRollupComputed(tenant_id=_uuid(), rollup_date=date.today()))

    def test_anomaly_detected_metric_and_thresholds(self):
        from corpmind.modules.analytics.events import AnomalyDetected
        evt = AnomalyDetected(
            tenant_id=_uuid(), metric="reply_rate",
            value=0.01, threshold=0.05,
        )
        assert evt.metric == "reply_rate"
        assert evt.value == pytest.approx(0.01)
        assert evt.threshold == pytest.approx(0.05)
        _assert_utc_datetime(evt)

    def test_anomaly_detected_is_frozen(self):
        from corpmind.modules.analytics.events import AnomalyDetected
        _assert_frozen(
            AnomalyDetected(tenant_id=_uuid(), metric="cost", value=50.0, threshold=40.0)
        )


# ── Billing ───────────────────────────────────────────────────────────────────

class TestBillingEvents:
    def test_budget_threshold_reached_fields(self):
        from corpmind.modules.billing.events import BudgetThresholdReached
        evt = BudgetThresholdReached(
            tenant_id=_uuid(), threshold_pct=85,
            spend_inr=340.0, budget_inr=400.0,
        )
        assert evt.threshold_pct == 85
        assert evt.spend_inr == pytest.approx(340.0)
        assert evt.budget_inr == pytest.approx(400.0)
        _assert_utc_datetime(evt)

    def test_budget_threshold_pct_values(self):
        from corpmind.modules.billing.events import BudgetThresholdReached
        for pct in (70, 85, 95, 100):
            evt = BudgetThresholdReached(
                tenant_id=_uuid(), threshold_pct=pct,
                spend_inr=1.0, budget_inr=100.0,
            )
            assert evt.threshold_pct == pct

    def test_budget_threshold_is_frozen(self):
        from corpmind.modules.billing.events import BudgetThresholdReached
        _assert_frozen(
            BudgetThresholdReached(
                tenant_id=_uuid(), threshold_pct=70,
                spend_inr=28.0, budget_inr=40.0,
            )
        )

    def test_subscription_renewed_fields(self):
        from corpmind.modules.billing.events import SubscriptionRenewed
        end = datetime.now(UTC)
        evt = SubscriptionRenewed(tenant_id=_uuid(), plan_tier="growth", new_period_end=end)
        assert evt.plan_tier == "growth"
        assert evt.new_period_end == end
        _assert_utc_datetime(evt)

    def test_subscription_renewed_is_frozen(self):
        from corpmind.modules.billing.events import SubscriptionRenewed
        _assert_frozen(
            SubscriptionRenewed(
                tenant_id=_uuid(), plan_tier="starter",
                new_period_end=datetime.now(UTC),
            )
        )
