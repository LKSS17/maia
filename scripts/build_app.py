"""Script para compilação e empacotamento do executável único MAIA."""

import os
import subprocess
import sys


def build():
    print("Iniciando build do executável MAIA via PyInstaller...")
    
    # os.pathsep resolve para ';' no Windows e ':' no Linux/macOS
    backend_data = f"{os.path.abspath('backend')}{os.pathsep}backend"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "MAIA",
        "--add-data", backend_data,
        "--hidden-import", "customtkinter",
        "--hidden-import", "openpyxl",
        "--hidden-import", "ofxparse",
        "--hidden-import", "pdfplumber",
        "--hidden-import", "sqlalchemy",
        "--hidden-import", "platformdirs",
        "backend/app/gui.py"
    ]
    subprocess.run(cmd, check=True)
    print("Build concluído com sucesso na pasta 'dist/MAIA'!")


if __name__ == "__main__":
    build()