"""Append 5 more training tests."""
import pathlib

path = pathlib.Path(__file__).parent / "test_training_service.py"

extra = r"""

# ── Final coverage tests ──────────────────────────────────────────────────────

class TestFinalCoverage:
    def test_valid_priorities_set(self):
        from corpmind.modules.training.schemas import VALID_PRIORITIES
        assert "low" in VALID_PRIORITIES
        assert "medium" in VALID_PRIORITIES
        assert "high" in VALID_PRIORITIES
        assert "urgent" in VALID_PRIORITIES

    def test_engagement_out_has_all_date_fields(self):
        from corpmind.modules.training.schemas import TrainingEngagementOut
        e = _engagement(
            actual_start_date=_TODAY,
            actual_end_date=_TODAY,
        )
        out = TrainingEngagementOut.model_validate(e)
        assert out.actual_start_date == _TODAY
        assert out.actual_end_date == _TODAY

    def test_engagement_out_participant_counts(self):
        from corpmind.modules.training.schemas import TrainingEngagementOut
        e = _engagement(estimated_participants=50, actual_participants=47)
        out = TrainingEngagementOut.model_validate(e)
        assert out.estimated_participants == 50
        assert out.actual_participants == 47

    def test_update_program_name_only(self):
        from corpmind.modules.training.schemas import TrainingEngagementUpdate
        u = TrainingEngagementUpdate(program_name="Revised Program")
        d = u.model_dump(exclude_none=True)
        assert list(d.keys()) == ["program_name"]

    def test_cancel_engagement_no_notes(self):
        from corpmind.modules.training.schemas import CancelEngagement
        c = CancelEngagement()
        assert c.notes is None
"""

with open(path, "a", encoding="utf-8") as f:
    f.write(extra)
print("ok")
