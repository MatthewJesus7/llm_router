import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock
import requests

from llms.ai_core import AIProvider, ProviderManager

class TestAIProvider:
    def test_has_key_with_key_present(self, monkeypatch):
        monkeypatch.setenv("TEST_API_KEY", "secret-key")
        provider = AIProvider(
            name="test",
            api_key_env="TEST_API_KEY",
            endpoint="https://api.test.com",
            make_headers=lambda k: {"Authorization": f"Bearer {k}"},
            build_payload=lambda p, t: {"prompt": p, "temperature": t},
            parse_response=lambda r: r.json()["text"]
        )
        assert provider.has_key() is True

    def test_has_key_without_key(self):
        provider = AIProvider(
            name="test",
            api_key_env="NONEXISTENT_KEY",
            endpoint="https://api.test.com",
            make_headers=lambda k: {},
            build_payload=lambda p, t: {},
            parse_response=lambda r: ""
        )
        assert provider.has_key() is False

    def test_reset_window_if_needed(self):
        provider = AIProvider(
            name="test",
            api_key_env="TEST",
            endpoint="https://api.test.com",
            make_headers=lambda k: {},
            build_payload=lambda p, t: {},
            parse_response=lambda r: ""
        )
        
        # Set window to old time
        old_time = time.time() - 100
        provider.window_start = old_time
        provider.used_count = 50
        
        provider.reset_window_if_needed()
        
        assert provider.window_start > old_time
        assert provider.used_count == 0

    def test_can_use_when_available(self):
        provider = AIProvider(
            name="test",
            api_key_env="TEST",
            endpoint="https://api.test.com",
            make_headers=lambda k: {},
            build_payload=lambda p, t: {},
            parse_response=lambda r: ""
        )
        provider.used_count = 5
        provider.usage_limit = 10
        
        assert provider.can_use() is True

    def test_can_use_when_exhausted(self):
        provider = AIProvider(
            name="test",
            api_key_env="TEST",
            endpoint="https://api.test.com",
            make_headers=lambda k: {},
            build_payload=lambda p, t: {},
            parse_response=lambda r: ""
        )
        provider.used_count = 15
        provider.usage_limit = 10
        
        assert provider.can_use() is False

    def test_can_use_when_temporarily_exhausted(self):
        provider = AIProvider(
            name="test",
            api_key_env="TEST",
            endpoint="https://api.test.com",
            make_headers=lambda k: {},
            build_payload=lambda p, t: {},
            parse_response=lambda r: ""
        )
        provider.exhausted_until = time.time() + 60
        
        assert provider.can_use() is False

    def test_mark_usage(self):
        provider = AIProvider(
            name="test",
            api_key_env="TEST",
            endpoint="https://api.test.com",
            make_headers=lambda k: {},
            build_payload=lambda p, t: {},
            parse_response=lambda r: ""
        )
        provider.used_count = 5
        provider.usage_limit = 10
        
        provider.mark_usage(2)
        
        assert provider.used_count == 7
        assert provider.exhausted_until == 0.0  # Not exhausted yet

    def test_mark_usage_reaching_limit(self):
        provider = AIProvider(
            name="test",
            api_key_env="TEST",
            endpoint="https://api.test.com",
            make_headers=lambda k: {},
            build_payload=lambda p, t: {},
            parse_response=lambda r: ""
        )
        provider.used_count = 9
        provider.usage_limit = 10
        original_window_start = provider.window_start
        
        provider.mark_usage(2)  # Should exceed limit
        
        assert provider.used_count == 11
        assert provider.exhausted_until == original_window_start + provider.window_seconds

    def test_force_exhaust(self):
        provider = AIProvider(
            name="test",
            api_key_env="TEST",
            endpoint="https://api.test.com",
            make_headers=lambda k: {},
            build_payload=lambda p, t: {},
            parse_response=lambda r: ""
        )
        
        provider.force_exhaust(30)
        
        assert provider.exhausted_until > time.time()

    @patch('requests.post')
    def test_send_success(self, mock_post, monkeypatch):
        monkeypatch.setenv("TEST_API_KEY", "secret-key")
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        provider = AIProvider(
            name="test",
            api_key_env="TEST_API_KEY",
            endpoint="https://api.test.com",
            make_headers=lambda k: {"Authorization": f"Bearer {k}"},
            build_payload=lambda p, t: {"prompt": p, "temperature": t},
            parse_response=lambda r: r.json()["text"]
        )
        
        response = provider.send("test prompt", 0.7)
        
        mock_post.assert_called_once()
        assert response == mock_response

    def test_send_without_api_key(self):
        provider = AIProvider(
            name="test",
            api_key_env="MISSING_KEY",
            endpoint="https://api.test.com",
            make_headers=lambda k: {},
            build_payload=lambda p, t: {},
            parse_response=lambda r: ""
        )
        
        with pytest.raises(RuntimeError, match="API key for test not found"):
            provider.send("test prompt")


class TestProviderManager:
    def create_mock_provider(self, name, can_use=True, has_key=True):
        provider = Mock(spec=AIProvider)
        provider.name = name
        provider.can_use.return_value = can_use
        provider.has_key.return_value = has_key
        provider.usage_limit = 10
        provider.used_count = 0
        provider.window_seconds = 60
        provider.window_start = time.time()
        provider.exhausted_until = 0.0
        provider.lock = threading.Lock()
        return provider

    def test_init_filters_providers_without_keys(self):
        provider_with_key = self.create_mock_provider("with_key", has_key=True)
        provider_without_key = self.create_mock_provider("without_key", has_key=False)
        
        manager = ProviderManager([provider_with_key, provider_without_key])
        
        assert len(manager.providers) == 1
        assert manager.providers[0].name == "with_key"

    def test_init_no_providers_available(self):
        provider_without_key = self.create_mock_provider("test", has_key=False)
        
        with pytest.raises(RuntimeError, match="Nenhum provider configurado"):
            ProviderManager([provider_without_key])

    def test_get_available_provider_round_robin(self):
        provider1 = self.create_mock_provider("provider1")
        provider2 = self.create_mock_provider("provider2")
        
        manager = ProviderManager([provider1, provider2])
        
        # First call should return provider1 (starts at index 0)
        first = manager.get_available_provider()
        assert first.name == "provider1"
        
        # Second call should return provider2
        second = manager.get_available_provider()
        assert second.name == "provider2"
        
        # Third call should wrap around to provider1
        third = manager.get_available_provider()
        assert third.name == "provider1"

    def test_get_available_provider_skips_unavailable(self):
        provider1 = self.create_mock_provider("provider1", can_use=False)
        provider2 = self.create_mock_provider("provider2", can_use=True)
        
        manager = ProviderManager([provider1, provider2])
        
        result = manager.get_available_provider()
        assert result.name == "provider2"

    def test_get_available_provider_none_available(self):
        provider1 = self.create_mock_provider("provider1", can_use=False)
        provider2 = self.create_mock_provider("provider2", can_use=False)
        
        manager = ProviderManager([provider1, provider2])
        
        result = manager.get_available_provider()
        assert result is None

    @patch('requests.post')
    def test_ask_success(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "response text"}
        mock_post.return_value = mock_response
        
        provider = self.create_mock_provider("test_provider")
        provider.send.return_value = mock_response
        provider.parse_response.return_value = "response text"
        
        manager = ProviderManager([provider])
        
        result = manager.ask("test prompt", 0.7)
        
        assert result == "response text"
        provider.mark_usage.assert_called_once_with(1)

    @patch('requests.post')
    def test_ask_rate_limit_handling(self, mock_post):
        # First provider gets rate limited, second succeeds
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"text": "success response"}
        
        provider1 = self.create_mock_provider("provider1")
        provider2 = self.create_mock_provider("provider2")
        
        # Make provider1 fail with 429, provider2 succeed
        provider1.send.return_value = mock_response_429
        provider2.send.return_value = mock_response_200
        provider2.parse_response.return_value = "success response"
        
        manager = ProviderManager([provider1, provider2])
        
        result = manager.ask("test prompt")
        
        assert result == "success response"
        provider1.force_exhaust.assert_called_once()
        provider2.mark_usage.assert_called_once_with(1)

    def test_ask_all_providers_fail(self):
        provider1 = self.create_mock_provider("provider1")
        provider2 = self.create_mock_provider("provider2")
        
        # Both providers will be unavailable
        provider1.can_use.return_value = False
        provider2.can_use.return_value = False
        
        manager = ProviderManager([provider1, provider2])
        
        with pytest.raises(RuntimeError, match="Todos providers falharam"):
            manager.ask("test prompt")


# Testes de integração (opcionais, mas úteis)
class TestIntegration:
    def test_thread_safety(self):
        """Testa se o provider é thread-safe"""
        provider = AIProvider(
            name="test",
            api_key_env="TEST",
            endpoint="https://api.test.com",
            make_headers=lambda k: {},
            build_payload=lambda p, t: {},
            parse_response=lambda r: ""
        )
        
        results = []
        errors = []
        
        def worker():
            try:
                # Esta operação deve ser thread-safe
                with provider.lock:
                    provider.used_count += 1
                    results.append(provider.used_count)
            except Exception as e:
                errors.append(e)
        
        threads = []
        for _ in range(10):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert provider.used_count == 10

        # Para rodar: pytest test_ai_core.py -v
        # ou: pytest llms/tests/test_ai_core.py -v