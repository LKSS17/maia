"""Módulo de integração com provedores de nuvem (Google Drive e Microsoft OneDrive)."""

import io
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import requests

from backend.app.core.logging import logger
from backend.app.core.security import vault


class CloudStorageProvider(ABC):
    """Interface padrão para operações em nuvem do MAIA."""

    @abstractmethod
    def upload_file(self, file_bytes: bytes, filename: str, folder_id: Optional[str] = None) -> Dict[str, Any]:
        """Faz upload de arquivo diretamente da memória."""
        pass

    @abstractmethod
    def create_folder(self, folder_name: str, parent_folder_id: Optional[str] = None) -> str:
        """Cria uma pasta e retorna seu identificador único na nuvem."""
        pass

    @abstractmethod
    def get_or_create_client_path(self, client_name: str, year: int, month: int) -> str:
        """Garante a estrutura Clientes/[Nome]/[Ano]/[Mês]/ e retorna o folder_id final."""
        pass


class GoogleDriveService(CloudStorageProvider):
    """Implementação para Google Drive usando OAuth 2.0 e escopo restrito drive.file."""

    def __init__(self, service_resource=None):
        self.service = service_resource

    def create_folder(self, folder_name: str, parent_folder_id: Optional[str] = None) -> str:
        if not self.service:
            raise ValueError("Google Drive não está autenticado.")

        file_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_folder_id:
            file_metadata["parents"] = [parent_folder_id]

        folder = self.service.files().create(body=file_metadata, fields="id").execute()
        return folder.get("id")

    def upload_file(self, file_bytes: bytes, filename: str, folder_id: Optional[str] = None) -> Dict[str, Any]:
        if not self.service:
            raise ValueError("Google Drive não está autenticado.")

        from googleapiclient.http import MediaIoBaseUpload

        file_metadata = {"name": filename}
        if folder_id:
            file_metadata["parents"] = [folder_id]

        media = MediaIoBaseUpload(
            io.BytesIO(file_bytes),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            resumable=True
        )

        file = self.service.files().create(
            body=file_metadata, media_body=media, fields="id, name, webViewLink"
        ).execute()

        logger.info(f"Upload concluído no Google Drive: Arquivo ID {file.get('id')}")
        return {
            "provider": "google_drive",
            "file_id": file.get("id"),
            "file_name": file.get("name"),
            "web_link": file.get("webViewLink")
        }

    def get_or_create_client_path(self, client_name: str, year: int, month: int) -> str:
        # Hierarquia: Clientes -> [Nome] -> [Ano] -> [Mês]
        clientes_root_id = self.create_folder("Clientes")
        client_dir_id = self.create_folder(client_name, parent_folder_id=clientes_root_id)
        year_dir_id = self.create_folder(str(year), parent_folder_id=client_dir_id)
        month_dir_id = self.create_folder(f"{month:02d}", parent_folder_id=year_dir_id)
        return month_dir_id


class OneDriveService(CloudStorageProvider):
    """Implementação para Microsoft OneDrive via Microsoft Graph API."""

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token
        self.base_url = "https://graph.microsoft.com/v1.0"

    def _headers(self) -> Dict[str, str]:
        if not self.access_token:
            raise ValueError("OneDrive não está autenticado.")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    def create_folder(self, folder_name: str, parent_folder_id: Optional[str] = None) -> str:
        url = (
            f"{self.base_url}/me/drive/items/{parent_folder_id}/children"
            if parent_folder_id else f"{self.base_url}/me/drive/root/children"
        )
        payload = {
            "name": folder_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "rename"
        }
        res = requests.post(url, headers=self._headers(), json=payload, timeout=15)
        res.raise_for_status()
        return res.json().get("id")

    def upload_file(self, file_bytes: bytes, filename: str, folder_id: Optional[str] = None) -> Dict[str, Any]:
        url = (
            f"{self.base_url}/me/drive/items/{folder_id}:/{filename}:/content"
            if folder_id else f"{self.base_url}/me/drive/root:/{filename}:/content"
        )
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        }
        res = requests.put(url, headers=headers, data=file_bytes, timeout=30)
        res.raise_for_status()
        data = res.json()

        logger.info(f"Upload concluído no OneDrive: Arquivo ID {data.get('id')}")
        return {
            "provider": "onedrive",
            "file_id": data.get("id"),
            "file_name": data.get("name"),
            "web_link": data.get("webUrl")
        }

    def get_or_create_client_path(self, client_name: str, year: int, month: int) -> str:
        clientes_root_id = self.create_folder("Clientes")
        client_dir_id = self.create_folder(client_name, parent_folder_id=clientes_root_id)
        year_dir_id = self.create_folder(str(year), parent_folder_id=client_dir_id)
        month_dir_id = self.create_folder(f"{month:02d}", parent_folder_id=year_dir_id)
        return month_dir_id
