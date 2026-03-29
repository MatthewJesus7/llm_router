import pytest
import os
import logging
from unittest.mock import patch, Mock

@pytest.fixture(autouse=True)
def setup_logging():
    """Configura logging para testes"""
    logging.basicConfig(level=logging.CRITICAL)  # Reduz noise durante testes

@pytest.fixture(autouse=True)
def clean_env():
    """Limpa environment variables entre testes"""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)

@pytest.fixture
def mock_google_response():
    """Fixture para resposta mock do Google AI"""
    def _create_response(text="Test response", status_code=200):
        mock_resp = Mock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": text}]
                }
            }]
        }
        mock_resp.text = f'{{"candidates": [{{"content": {{"parts": [{{"text": "{text}"}}]}}}}]}}'
        return mock_resp
    return _create_response

    # Para executar: pytest test_ai_router_check.py -v
    # ou: pytest -m llms.tests.test_ai_router_check.py -v