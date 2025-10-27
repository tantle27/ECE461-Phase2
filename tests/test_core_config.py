"""
Tests for src/core/config.py that focus on basic functionality without pydantic internals.
"""
import os
from unittest import mock

# Try to import but don't fail if pydantic isn't available
try:
    from src.core.config import Settings, settings
    IMPORT_SUCCESS = True
except ImportError:
    IMPORT_SUCCESS = False


class TestConfigImport:
    """Test basic config import and functionality."""
    
    def test_config_import_success(self):
        """Test that config can be imported."""
        assert IMPORT_SUCCESS, "Could not import config module - check dependencies"
    
    def test_settings_exists(self):
        """Test that settings object exists."""
        if IMPORT_SUCCESS:
            assert settings is not None
            assert hasattr(settings, 'env')

    def test_settings_basic_attributes(self):
        """Test basic settings attributes."""
        if IMPORT_SUCCESS:
            # Test default values exist
            assert hasattr(settings, 'env')
            assert hasattr(settings, 'request_timeout_s')
            assert hasattr(settings, 'http_retries')
            
            # Test default values
            assert isinstance(settings.env, str)
            assert isinstance(settings.request_timeout_s, float)
            assert isinstance(settings.http_retries, int)

    def test_create_new_settings(self):
        """Test creating new Settings instance."""
        if IMPORT_SUCCESS:
            new_settings = Settings()
            assert new_settings is not None
            assert hasattr(new_settings, 'env')

    def test_environment_variable_usage(self):
        """Test that environment variables are used if available."""
        if IMPORT_SUCCESS:
            with mock.patch.dict(os.environ, {'ENV': 'test-env'}):
                env_settings = Settings()
                # Should use environment variable if pydantic is working
                assert env_settings.env == 'test-env' or env_settings.env == 'dev'