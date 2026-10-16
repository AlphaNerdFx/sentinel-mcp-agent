"""
tests/unit/agent/test_model_adapter.py
Verifies Model Provider Adapter: local Ollama vs cloud fallback and timeout configuration.
Contract Reference: SPEC_V1.md COMP-02; PRD_V1.md Section 5.1, ADR-04, ADR-10.
"""

from unittest.mock import MagicMock, patch

from src.agent.model_adapter import get_model, is_ollama_online


class TestModelAdapter:
    def test_ollama_online_detection_success(self):
        """[Certain] Verifies that an HTTP 200 from Ollama version endpoint flags online."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert is_ollama_online() is True

    def test_ollama_offline_detection_failure(self):
        """[Certain] Verifies that connection timeouts or refusals flag offline."""
        with patch("urllib.request.urlopen", side_effect=Exception("Connection Refused")):
            assert is_ollama_online() is False

    @patch("src.agent.model_adapter.is_ollama_online", return_value=True)
    def test_get_model_local_ollama_configuration(self, mock_online):
        """[Certain] Verifies local path points to Ollama endpoint with temperature 0.0."""
        model = get_model(temperature=0.0)
        assert model.model_name == "qwen2.5:7b-instruct-q4_K_M"
        assert model.temperature == 0.0
        assert "localhost:11434" in str(model.openai_api_base)

    @patch("src.agent.model_adapter.is_ollama_online", return_value=False)
    def test_get_model_cloud_fallback_configuration(self, mock_online, monkeypatch):
        """[Certain] Verifies cloud fallback activates gpt-4o-mini when Ollama is offline."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-key-12345")
        model = get_model(temperature=0.0)
        assert model.model_name == "gpt-4o-mini"
        assert model.temperature == 0.0

    def test_transport_deadline_timeout_resolution(self, monkeypatch):
        """[Certain] Verifies MODEL_TIMEOUT env var configures HTTP socket timeout."""
        monkeypatch.setenv("MODEL_TIMEOUT", "60.0")
        with patch("src.agent.model_adapter.is_ollama_online", return_value=True):
            model = get_model()
            assert model.request_timeout == 60.0
