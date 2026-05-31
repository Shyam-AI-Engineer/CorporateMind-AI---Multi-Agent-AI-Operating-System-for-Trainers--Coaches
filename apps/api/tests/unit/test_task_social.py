"""Unit tests for workers/tasks/social.py — publish_scheduled_posts."""

from __future__ import annotations

from unittest.mock import patch

from corpmind.workers.tasks.social import publish_scheduled_posts


class TestPublishScheduledPosts:
    def test_noop_returns_none(self):
        result = publish_scheduled_posts.run()
        assert result is None

    def test_logs_noop_event(self):
        with patch("corpmind.workers.tasks.social.log") as mock_log:
            publish_scheduled_posts.run()
        mock_log.info.assert_called_once_with("social.publish_scheduled_posts.noop")
