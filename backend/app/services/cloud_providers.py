"""Módulo de integração com provedores de nuvem (Google Drive e Microsoft OneDrive)."""

import io
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import requests

from backend.app.core.logging import logger


class CloudStorageProvider(ABC):
    @abstractmethod
    def upload_file(self, file_bytes: bytes, filename: str, folder_id: Optional[str] = None) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_or_create_folder(self, folder_name: str, parent_folder_id: Optional[str] = None) -> str:
        pass

    @abstractmethod
    def get_or_create_client_path(self, client_name: str, year: int, month: int) -> str:
        pass


class GoogleDriveService(CloudStorageProvider):
    def __init__(self, service_resource=None):
        self.service = service_resource

    def get_or_create_folder(self, folder_name: str, parent_folder_id: Optional[str] = None) -> str:
        """Busca se a pasta já existe. Se não existir, cria uma única vez."""
        if not self.service:
            raise ValueError("Google Drive não está autenticado.")

        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if parent_folder_id:
            query += f" and '{parent_folder_id}' in parents"

        response = self.service.files().list(
            q=query, spaces='drive', fields='files(id, name)'
        ).execute()
        files = response.get('files', [])

        if files:
            return files[0].get('id')

        # Criação se não existir
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
        clientes_root_id = self.get_or_create_folder("Clientes")
        client_dir_id = self.get_or_create_folder(client_name, parent_folder_id=clientes_root_id)
        year_dir_id = self.get_or_create_folder(str(year), parent_folder_id=client_dir_id)
        month_dir_id = self.get_or_create_folder(f"{month:02d}", parent_folder_id=year_dir_id)
        return month_dir_id


class OneDriveService(CloudStorageProvider):
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

    def get_or_create_folder(self, folder_name: str, parent_folder_id: Optional[str] = None) -> str:
        """Verifica se o item filho existe antes de solicitar criação."""
        list_url = (
            f"{self.base_url}/me/drive/items/{parent_folder_id}/children"
            if parent_folder_id else f"{self.base_url}/me/drive/root/children"
        )
        
        try:
            res = requests.get(list_url, headers=self._headers(), timeout=10)
            if res.status_code == 200:
                items = res.json().get("value", [])
                for item in items:
                    if item.get("name") == folder_name and "folder" in item:
                        return item.get("id")
        except Exception:
            pass

        # Criação com conflictBehavior fail para garantir unicidade
        payload = {
            "name": folder_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail"
        }
        create_res = requests.post(list_url, headers=self._headers(), json=payload, timeout=15)
        if create_res.status_code in (200, 201):
            return create_res.json().get("id")
        elif create_res.status_code == 409:
            # Se conflitou por corrida, re-busca o ID
            res = requests.get(list_url, headers=self._headers(), timeout=10)
            for item in res.json().get("value", []):
                if item.get("name") == folder_name:
                    return item.get("id")

        create_res.raise_for_status()
        return create_res.json().get("id")

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
        clientes_root_id = self.get_or_create_folder("Clientes")
        client_dir_id = self.get_or_create_folder(client_name, parent_folder_id=clientes_root_id)
        year_dir_id = self.get_or_create_folder(str(year), parent_folder_id=client_dir_id)
        month_dir_id = self.get_or_create_folder(f"{month:02d}", parent_folder_id=year_dir_id)
        return month_dir_id