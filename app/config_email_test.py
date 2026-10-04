import os
import unittest
from unittest.mock import patch

from app.config import Config

REQUIRED = {
    "LOG_LEVEL": "INFO",
    "CASBIN_LOG_LEVEL": "INFO",
    "SQLALCHEMY_LOG_LEVEL": "WARNING",
    "ENVIRONMENT": "test",
    "POSTGRES_HOST": "db",
    "POSTGRES_PORT": "5432",
    "POSTGRES_USER": "user",
    "POSTGRES_PASSWORD": "password",
    "POSTGRES_DB": "db",
    "AUTH_FILE_UPLOAD_TOKEN_SECRET": "secret",
    "AUTH_CLIENT_SECRET_PEPPER": "pepper-of-sixteen-chars",
    "AUTH_PASSWORD_PEPPER": "password-pepper-of-sixteen",
    "AUTH_CHALLENGE_PEPPER": "challenge-pepper-of-sixteen",
    "CASBIN_MODEL_FILE": "app/resources/casbin_model.conf",
    "DOI_BASE_URL": "http://doi",
    "DOI_PREFIX": "10.0",
    "DOI_LOGIN": "login",
    "DOI_PASSWORD": "password",
    "MINIO_URL": "minio:9000",
    "MINIO_ACCESS_KEY": "key",
    "MINIO_SECRET_KEY": "secret",
    "MINIO_DATASET_BUCKET": "datamap",
    "MINIO_DEFAULT_REGION_ID": "us-east-1",
    "MINIO_USE_SSL": "False",
}


class TestEmailSettings(unittest.TestCase):
    def build(self, **overrides) -> Config:
        with patch.dict(os.environ, {**REQUIRED, **overrides}, clear=True):
            return Config(_env_file=None)

    def test_an_environment_without_email_settings_still_starts_with_sending_off(self):
        config = self.build()

        self.assertFalse(config.EMAIL_ENABLED)
        self.assertEqual(config.EMAIL_FROM_NAME, "DataMap")
        self.assertEqual(config.SMTP_PORT, 587)
        self.assertEqual(config.SMTP_TIMEOUT_SECONDS, 10)
        self.assertTrue(config.SMTP_STARTTLS)
        self.assertIsNone(config.SMTP_USERNAME)
        self.assertEqual(config.PUBLIC_BASE_URL, "https://datamap.pcs.usp.br")
        self.assertEqual(config.BUILD_COMMIT, "unknown")

    def test_the_production_values_are_read_as_written(self):
        config = self.build(
            EMAIL_ENABLED="true",
            EMAIL_FROM_NAME="DataMap",
            EMAIL_FROM_ADDRESS="datamap.pcs@gmail.com",
            SMTP_HOST="smtp.gmail.com",
            SMTP_PORT="587",
            SMTP_STARTTLS="true",
            SMTP_USERNAME="datamap.pcs@gmail.com",
            SMTP_PASSWORD="abcdabcdabcdabcd",
        )

        self.assertTrue(config.EMAIL_ENABLED)
        self.assertEqual(config.EMAIL_FROM_ADDRESS, "datamap.pcs@gmail.com")
        self.assertEqual(config.SMTP_HOST, "smtp.gmail.com")
        self.assertEqual(config.SMTP_PASSWORD, "abcdabcdabcdabcd")
