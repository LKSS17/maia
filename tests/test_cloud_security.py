"""Testes de criptografia de tokens e resiliência de serviços em nuvem."""

import pytest
from unittest.mock import MagicMock, patch
from backend.app.core.security import TokenVault
from backend.app.services.cloud_providers import GoogleDriveService, OneDriveService


def test_token_vault_encryption_cycle():
    vault = TokenVault()
    secret_token = "ya29.a0AfH6SMA-test-oauth-token-123456"

    encrypted = vault.encrypt(secret_token)
    assert encrypted != secret_token
    assert len(encrypted) > len(secret_token)

    decrypted = vault.decrypt(encrypted)
    assert decrypted == secret_token


def test_google_drive_upload_flow():
    mock_service = MagicMock()
    mock_files = MagicMock()
    mock_service.files.return_value = mock_files

    mock_files.create.return_value.execute.return_value = {
        "id": "drive_file_999",
        "name": "Cliente_Conciliacao_2026-05.xlsx",
        "webViewLink": "https://drive.google.com/file/d/drive_file_999/view"
    }

    gdrive = GoogleDriveService(service_resource=mock_service)
    dummy_bytes = b"EXCEL_DATA_STREAM"

    result = gdrive.upload_file(dummy_bytes, "Cliente_Conciliacao_2026-05.xlsx", folder_id="folder_123")

    assert result["provider"] == "google_drive"
    assert result["file_id"] == "drive_file_999"
    assert result["web_link"] == "https://drive.google.com/file/d/drive_file_999/view"


def test_onedrive_upload_flow():
    with patch("requests.put") as mock_put:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "onedrive_item_888",
            "name": "Conciliacao.xlsx",
            "webUrl": "https://onedrive.live.com/view?id=onedrive_item_888"
        }
        mock_response.status_code = 201
        mock_put.return_value = mock_response

        onedrive = OneDriveService(access_token="valid_mock_token")
        result = onedrive.upload_file(b"EXCEL_BYTES", "Conciliacao.xlsx", folder_id="folder_abc")

        assert result["provider"] == "onedrive"
        assert result["file_id"] == "onedrive_item_888"
        assert "webUrl" not in result or result["web_link"] is not None
