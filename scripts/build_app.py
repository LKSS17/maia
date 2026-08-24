"""Script para compilação e empacotamento do executável único MAIA."""

import os
import subprocess
import sys


def build():
    print("Iniciando build do executável MAIA via PyInstaller...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "MAIA",
        "--add-data", f"{os.path.abspath('backend')}:backend",
        "--hidden-import", "customtkinter",
        "--hidden-import", "openpyxl",
        "--hidden-import", "ofxparse",
        "--hidden-import", "pdfplumber",
        "--hidden-import", "sqlalchemy",
        "backend/app/gui.py"
    ]
    subprocess.run(cmd, check=True)
    print("Build concluído com sucesso na pasta 'dist/MAIA'!")


if __name__ == "__main__":
    build()
