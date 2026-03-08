"""Tests for authentication gate and settings persistence."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


class TestGetAppPassword:
    """Tests for _get_app_password() function."""

    @patch.dict(os.environ, {"APP_PASSWORD": "secret123"})
    def test_get_app_password_from_env(self):
        """When APP_PASSWORD env var is set, _get_app_password() returns it."""
        from ui.app import _get_app_password

        # Mock st.secrets to raise KeyError (no secrets.toml)
        with patch("ui.app.st") as mock_st:
            mock_st.secrets.__getitem__ = MagicMock(side_effect=KeyError("APP_PASSWORD"))
            result = _get_app_password()
        assert result == "secret123"

    def test_get_app_password_empty(self):
        """When no APP_PASSWORD configured, _get_app_password() returns empty string."""
        from ui.app import _get_app_password

        with patch("ui.app.st") as mock_st, \
             patch.dict(os.environ, {}, clear=False):
            mock_st.secrets.__getitem__ = MagicMock(side_effect=KeyError("APP_PASSWORD"))
            # Remove APP_PASSWORD if present
            os.environ.pop("APP_PASSWORD", None)
            result = _get_app_password()
        assert result == ""

    def test_get_app_password_from_secrets(self):
        """When st.secrets has APP_PASSWORD, it takes priority."""
        from ui.app import _get_app_password

        with patch("ui.app.st") as mock_st:
            mock_st.secrets.__getitem__ = MagicMock(return_value="from_secrets")
            result = _get_app_password()
        assert result == "from_secrets"


class TestCheckPassword:
    """Tests for check_password() function."""

    def test_check_password_no_password_configured(self):
        """When no password configured, check_password() returns True (allow access with warning)."""
        from ui.app import check_password

        with patch("ui.app._get_app_password", return_value=""), \
             patch("ui.app.st") as mock_st:
            mock_st.session_state = {}
            result = check_password()
        assert result is True
        mock_st.warning.assert_called_once()

    def test_check_password_correct(self):
        """When password matches, session state gets authenticated=True."""
        from ui.app import check_password

        session_state = {}
        with patch("ui.app._get_app_password", return_value="correct"), \
             patch("ui.app.st") as mock_st:
            mock_st.session_state = session_state
            mock_st.text_input.return_value = "correct"
            mock_st.button.return_value = True
            # check_password calls st.rerun() on success -- mock it
            mock_st.rerun.side_effect = Exception("rerun_called")
            with pytest.raises(Exception, match="rerun_called"):
                check_password()
        assert session_state["authenticated"] is True

    def test_check_password_already_authenticated(self):
        """When session_state['authenticated'] is True, returns True immediately."""
        from ui.app import check_password

        with patch("ui.app.st") as mock_st:
            mock_st.session_state = {"authenticated": True}
            result = check_password()
        assert result is True

    def test_check_password_incorrect(self):
        """When password is wrong, shows error and returns False."""
        from ui.app import check_password

        with patch("ui.app._get_app_password", return_value="correct"), \
             patch("ui.app.st") as mock_st:
            mock_st.session_state = {}
            mock_st.text_input.return_value = "wrong"
            mock_st.button.return_value = True
            result = check_password()
        assert result is False
        mock_st.error.assert_called_once()
