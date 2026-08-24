"""Interface Local do MAIA com FastAPI e Dashboard Contábil."""

import os
import io
import webbrowser
from decimal import Decimal
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
import uvicorn

from backend.app.db.session import SessionLocal, Base, engine
from backend.app.models.entities import Cliente, Transacao, PlanoContas
from backend.app.services.ingestion import StatementIngestionService
from backend.app.services.rules_engine import RulesEngineService
from backend.app.services.ai_classifier import GeminiClassifierService
from backend.app.services.spreadsheet_generator import SpreadsheetGeneratorService
from backend.app.services.review_service import ReviewService
from backend.app.services.review_dto import ManualCorrectionRequest
from backend.app.services.stocks_service import StocksService

# Inicializar DB
Base.metadata.create_all(bind=engine)

app = FastAPI(title="MAIA")

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>MAIA — Motor de Análise e Inteligência Contábil</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-100 min-h-screen text-slate-800">
  <header class="bg-slate-900 text-white p-4 shadow-md flex justify-between items-center">
    <div>
      <h1 class="text-xl font-bold tracking-wide">MAIA</h1>
      <p class="text-xs text-slate-400">Motor de Análise e Inteligência Contábil</p>
    </div>
    <div class="space-x-2">
      <button onclick="switchTab('conciliacao')" class="px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-700 text-sm font-medium">📂 Conciliação</button>
      <button onclick="switchTab('revisao')" class="px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-sm font-medium">🔍 Revisão</button>
      <button onclick="switchTab('acoes')" class="px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-sm font-medium">📈 Consulta Ações</button>
      <button onclick="switchTab('config')" class="px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-sm font-medium">☁️ Nuvem</button>
    </div>
  </header>

  <main class="max-w-6xl mx-auto p-6">
    <!-- ABA 1: CONCILIAÇÃO -->
    <section id="tab-conciliacao" class="tab-content bg-white p-6 rounded-lg shadow space-y-4">
      <h2 class="text-lg font-bold border-b pb-2">Processamento de Extratos Bancários</h2>
      <form id="form-ingest" class="space-y-4" enctype="multipart/form-data">
        <div>
          <label class="block text-sm font-medium text-slate-700">Selecione o Arquivo de Extrato (OFX, CSV ou PDF):</label>
          <input type="file" id="statement-file" name="file" required class="mt-1 block w-full border p-2 rounded">
        </div>
        <button type="button" onclick="processStatement()" class="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded font-semibold text-sm">Processar e Classificar com MAIA</button>
      </form>
      <div id="conciliacao-log" class="bg-slate-900 text-green-400 p-4 rounded text-sm font-mono whitespace-pre-wrap min-h-[140px]">Aguardando arquivo para processamento...</div>
    </section>

    <!-- ABA 2: REVISÃO -->
    <section id="tab-revisao" class="tab-content hidden bg-white p-6 rounded-lg shadow space-y-4">
      <div class="flex justify-between items-center border-b pb-2">
        <h2 class="text-lg font-bold">Lançamentos Pendentes de Revisão</h2>
        <button onclick="loadReviewItems()" class="bg-slate-800 text-white px-3 py-1.5 rounded text-sm">Atualizar Pendências</button>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm text-left border">
          <thead class="bg-slate-200 uppercase text-xs">
            <tr>
              <th class="p-3">ID</th>
              <th class="p-3">Data</th>
              <th class="p-3">Histórico</th>
              <th class="p-3">Valor</th>
              <th class="p-3">Confiança</th>
              <th class="p-3">Ações</th>
            </tr>
          </thead>
          <tbody id="review-table-body" class="divide-y">
            <tr><td colspan="6" class="p-4 text-center text-slate-500">Clique em "Atualizar Pendências" para carregar.</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- ABA 3: AÇÕES -->
    <section id="tab-acoes" class="tab-content hidden bg-white p-6 rounded-lg shadow space-y-4">
      <h2 class="text-lg font-bold border-b pb-2">Consulta de Ações e CNPJ CVM</h2>
      <div class="flex gap-2">
        <input type="text" id="stock-term" placeholder="Digite ticker ou nome (ex: Petrobras, VALE3, ITUB4)" class="border p-2 rounded flex-1">
        <button onclick="searchStock()" class="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded text-sm font-semibold">Consultar</button>
      </div>
      <div id="stock-result" class="bg-slate-50 border p-4 rounded text-sm space-y-2">
        Digite um ticker ou nome de companhia para consultar dados cadastrais oficiais e cotação.
      </div>
    </section>

    <!-- ABA 4: NUVEM -->
    <section id="tab-config" class="tab-content hidden bg-white p-6 rounded-lg shadow space-y-4">
      <h2 class="text-lg font-bold border-b pb-2">Integrações em Nuvem</h2>
      <div class="border p-4 rounded flex justify-between items-center bg-slate-50">
        <div>
          <h3 class="font-semibold">Google Drive</h3>
          <p class="text-xs text-slate-500">Escopo restrito drive.file configurado com criptografia local.</p>
        </div>
        <span class="bg-green-100 text-green-800 text-xs px-2.5 py-1 rounded font-semibold">Ativo</span>
      </div>
      <div class="border p-4 rounded flex justify-between items-center bg-slate-50">
        <div>
          <h3 class="font-semibold">Microsoft OneDrive</h3>
          <p class="text-xs text-slate-500">OAuth 2.0 via Microsoft Graph API.</p>
        </div>
        <span class="bg-green-100 text-green-800 text-xs px-2.5 py-1 rounded font-semibold">Ativo</span>
      </div>
    </section>
  </main>

  <script>
    function switchTab(tabName) {
      document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
      document.getElementById('tab-' + tabName).classList.remove('hidden');
    }

    async function processStatement() {
      const fileInput = document.getElementById('statement-file');
      if (!fileInput.files[0]) return alert('Selecione um arquivo primeiro.');

      const formData = new FormData();
      formData.append('file', fileInput.files[0]);

      const log = document.getElementById('conciliacao-log');
      log.innerText = 'Processando extrato, aplicando regras e inteligência contábil...\\n';

      try {
        const res = await fetch('/api/process', { method: 'POST', body: formData });
        const data = await res.json();
        if (res.ok) {
          log.innerText += `Sucesso!\\nArquivo: ${data.filename}\\nTransações: ${data.total}\\nPlanilha gerada: ${data.xlsx}\\n`;
        } else {
          log.innerText += `Erro: ${data.detail}\\n`;
        }
      } catch (err) {
        log.innerText += `Falha na requisição: ${err.message}\\n`;
      }
    }

    async function loadReviewItems() {
      const tbody = document.getElementById('review-table-body');
      tbody.innerHTML = '<tr><td colspan="6" class="p-4 text-center">Carregando...</td></tr>';
      const res = await fetch('/api/review/pending');
      const items = await res.json();
      if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="p-4 text-center text-slate-500">Nenhuma pendência encontrada.</td></tr>';
        return;
      }
      tbody.innerHTML = items.map(it => `
        <tr class="hover:bg-slate-50">
          <td class="p-3 font-semibold">${it.id}</td>
          <td class="p-3">${it.data}</td>
          <td class="p-3">${it.descricao_banco}</td>
          <td class="p-3 font-medium">R$ ${parseFloat(it.valor).toFixed(2)}</td>
          <td class="p-3"><span class="px-2 py-0.5 rounded text-xs ${it.nivel_confianca === 'ALTA' ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'}">${it.nivel_confianca}</span></td>
          <td class="p-3"><button onclick="approveTx(${it.id})" class="bg-blue-600 hover:bg-blue-700 text-white px-2 py-1 rounded text-xs">Aprovar</button></td>
        </tr>
      `).join('');
    }

    async function approveTx(id) {
      const res = await fetch(`/api/review/approve/${id}`, { method: 'POST' });
      if (res.ok) {
        alert('Transação aprovada com sucesso!');
        loadReviewItems();
      } else {
        alert('Erro ao aprovar.');
      }
    }

    async function searchStock() {
      const term = document.getElementById('stock-term').value.trim();
      if (!term) return;
      const box = document.getElementById('stock-result');
      box.innerHTML = 'Buscando informações da companhia e cotação...';
      const res = await fetch(`/api/stocks/search?term=${encodeURIComponent(term)}`);
      const data = await res.json();
      if (!data.resultados.length) {
        box.innerHTML = `Nenhum resultado encontrado para '${term}'.`;
        return;
      }
      box.innerHTML = data.resultados.map(q => `
        <div class="border-b pb-2 mb-2 last:border-0">
          <div class="font-bold text-base text-blue-900">${q.ticker} — ${q.nome_empresa}</div>
          <div class="grid grid-cols-2 gap-2 mt-1 text-xs text-slate-600">
            <div><strong>CNPJ Oficial CVM:</strong> ${q.cnpj || 'Não localizado'}</div>
            <div><strong>Preço Atual:</strong> R$ ${parseFloat(q.preco_atual).toFixed(2)}</div>
            <div><strong>Variação Dia:</strong> ${q.variacao_dia}%</div>
            <div><strong>Data/Hora:</strong> ${new Date(q.data_hora_consulta).toLocaleString()}</div>
          </div>
        </div>
      `).join('');
    }
  </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_CONTENT

@app.post("/api/process")
async def process_statement(file: UploadFile = File(...)):
    db = SessionLocal()
    try:
        content = await file.read()
        cliente = db.query(Cliente).first()
        if not cliente:
            cliente = Cliente(nome="Empresa Padrão", documento="00.000.000/0001-00")
            db.add(cliente)
            db.commit()
            db.refresh(cliente)

        ingestion_svc = StatementIngestionService(db)
        extrato, txs = ingestion_svc.ingest_statement(cliente.id, file.filename, content)

        rules_engine = RulesEngineService(db)
        pendentes_ia = []
        for t in txs:
            rules_engine.classify_transaction(t)
            if t.status_revisao.value == "pendente":
                pendentes_ia.append(t)

        if pendentes_ia:
            gemini_svc = GeminiClassifierService(db)
            gemini_svc.classify_batch(cliente.id, pendentes_ia)

        gen = SpreadsheetGeneratorService()
        out_name = gen.get_default_filename(cliente.nome)
        save_path = os.path.join(os.path.expanduser("~"), out_name)
        gen.generate_file(txs, save_path, cliente=cliente)

        return {"filename": file.filename, "total": len(txs), "xlsx": save_path}
    finally:
        db.close()

@app.get("/api/review/pending")
def list_pending():
    db = SessionLocal()
    try:
        cliente = db.query(Cliente).first()
        if not cliente:
            return []
        svc = ReviewService(db)
        items = svc.get_pending_review_items(cliente.id)
        return [it.model_dump() for it in items]
    finally:
        db.close()

@app.post("/api/review/approve/{tx_id}")
def approve_tx(tx_id: int):
    db = SessionLocal()
    try:
        svc = ReviewService(db)
        tx = svc.approve_transaction(tx_id)
        return {"status": "ok", "id": tx.id}
    finally:
        db.close()

@app.get("/api/stocks/search")
def search_stocks(term: str):
    svc = StocksService()
    res = svc.search_by_name_or_ticker(term)
    return res.model_dump()


def run():
    webbrowser.open("http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    run()
