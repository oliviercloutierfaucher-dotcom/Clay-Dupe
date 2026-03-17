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

    def test_check_password_no_password_blocks_in_production(self):
        """When no password configured in production, check_password() returns False."""
        from ui.app import check_password

        with patch("ui.app._get_app_password", return_value=""), \
             patch("ui.app._is_local_dev", return_value=False), \
             patch("ui.app.st") as mock_st:
            mock_st.session_state = {}
            result = check_password()
        assert result is False
        mock_st.error.assert_called_once()

    def test_check_password_no_password_allows_local_dev(self):
        """When no password configured locally, check_password() allows access."""
        from ui.app import check_password

        with patch("ui.app._get_app_password", return_value=""), \
             patch("ui.app._is_local_dev", return_value=True), \
             patch("ui.app.st") as mock_st:
            mock_st.session_state = {}
            result = check_password()
        assert result is True

    def test_check_password_correct(self):
        """When password matches, session state gets authenticated=True."""
        from ui.app import check_password
        from unittest.mock import MagicMock

        session_state = {}
        with patch("ui.app._get_app_password", return_value="correct"), \
             patch("ui.app.st") as mock_st:
            mock_st.session_state = session_state
            # st.columns returns 3 context-manageable column mocks
            mock_cols = [MagicMock(), MagicMock(), MagicMock()]
            for mc in mock_cols:
                mc.__enter__ = MagicMock(return_value=mc)
                mc.__exit__ = MagicMock(return_value=False)
            mock_st.columns.return_value = mock_cols
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
        from unittest.mock import MagicMock

        with patch("ui.app._get_app_password", return_value="correct"), \
             patch("ui.app.st") as mock_st:
            mock_st.session_state = {}
            # st.columns returns 3 context-manageable column mocks
            mock_cols = [MagicMock(), MagicMock(), MagicMock()]
            for mc in mock_cols:
                mc.__enter__ = MagicMock(return_value=mc)
                mc.__exit__ = MagicMock(return_value=False)
            mock_st.columns.return_value = mock_cols
            mock_st.text_input.return_value = "wrong"
            mock_st.button.return_value = True
            result = check_password()
        assert result is False
        mock_st.error.assert_called_once()


# ---------------------------------------------------------------------------
# Settings persistence tests
# ---------------------------------------------------------------------------


class TestPersistSettings:
    """Tests for persist_settings() function."""

    @patch("config.settings.load_dotenv")
    @patch("config.settings.set_key")
    def test_persist_settings_writes_env(self, mock_set_key, mock_load_dotenv):
        """persist_settings({"KEY": "val"}) calls set_key for each pair."""
        from config.settings import persist_settings, _ENV_PATH

        persist_settings({"MY_KEY": "my_value", "OTHER": "data"})

        assert mock_set_key.call_count == 2
        mock_set_key.assert_any_call(_ENV_PATH, "MY_KEY", "my_value")
        mock_set_key.assert_any_call(_ENV_PATH, "OTHER", "data")

    @patch("config.settings.load_dotenv")
    @patch("config.settings.set_key")
    def test_persist_settings_reloads_env(self, mock_set_key, mock_load_dotenv):
        """After persist_settings(), load_dotenv(override=True) is called."""
        from config.settings import persist_settings, _ENV_PATH

        persist_settings({"KEY": "val"})

        mock_load_dotenv.assert_called_with(_ENV_PATH, override=True)

    @patch("config.settings.load_dotenv")
    @patch("config.settings.set_key")
    def test_persist_settings_skips_none(self, mock_set_key, mock_load_dotenv):
        """persist_settings({"KEY": None}) does not call set_key for None values."""
        from config.settings import persist_settings

        persist_settings({"GOOD": "value", "SKIP": None})

        assert mock_set_key.call_count == 1
        mock_set_key.assert_called_once()
        args = mock_set_key.call_args[0]
        assert args[1] == "GOOD"

    @patch("config.settings.load_dotenv")
    @patch("config.settings.set_key")
    def test_persist_settings_waterfall_order(self, mock_set_key, mock_load_dotenv):
        """Waterfall order serialized as comma-separated string."""
        from config.settings import persist_settings, _ENV_PATH

        persist_settings({"WATERFALL_ORDER": "apollo,icypeas,findymail"})

        mock_set_key.assert_any_call(
            _ENV_PATH, "WATERFALL_ORDER", "apollo,icypeas,findymail"
        )
