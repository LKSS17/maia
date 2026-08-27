"""Interface Desktop do MAIA desenvolvida com CustomTkinter (Performance, Auditoria e UX)."""

import os
import threading
from tkinter import filedialog, messagebox
import customtkinter as ctk

from backend.app.db.session import SessionLocal, Base, engine
from backend.app.models.entities import Cliente, LogAuditoria, Transacao, StatusRevisao
from backend.app.services.ingestion import StatementIngestionService
from backend.app.services.rules_engine import RulesEngineService
from backend.app.services.ai_classifier import GeminiClassifierService
from backend.app.services.spreadsheet_generator import SpreadsheetGeneratorService
from backend.app.services.review_service import ReviewService
from backend.app.services.review_dto import ManualCorrectionRequest
from backend.app.services.stocks_service import StocksService

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class MaiaApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("MAIA — Motor de Análise e Inteligência Contábil")
        self.geometry("1020x720")
        self.minsize(900, 600)

        Base.metadata.create_all(bind=engine)

        self.spreadsheet_service = SpreadsheetGeneratorService()
        self.stocks_service = StocksService()
        self.ai_classifier = GeminiClassifierService()

        # Layout Principal com Abas
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=15)

        self.tab_conciliacao = self.tabview.add("📂 Conciliação")
        self.tab_revisao = self.tabview.add("🔍 Revisão")
        self.tab_auditoria = self.tabview.add("📋 Trilha de Auditoria")
        self.tab_acoes = self.tabview.add("📈 Ações & CVM")
        self.tab_config = self.tabview.add("⚙️ Nuvem & Config")

        self._setup_conciliacao_tab()
        self._setup_revisao_tab()
        self._setup_auditoria_tab()
        self._setup_acoes_tab()
        self._setup_config_tab()

    # ==================== HELPERS THREAD-SAFE ====================
    def _ui_log(self, text: str):
        self.after(0, lambda: self._append_log(text))

    def _append_log(self, text: str):
        self.txt_log.insert("end", text + "\n")
        self.txt_log.see("end")

    def _ui_progress(self, current: int, total: int):
        val = current / total if total > 0 else 0
        self.after(0, lambda: self.prog_bar.set(val))
        self.after(0, lambda: self.lbl_prog.configure(text=f"Processando: {current}/{total} ({int(val*100)}%)"))

    # ==================== ABA 1: CONCILIAÇÃO ====================
    def _setup_conciliacao_tab(self):
        frame = self.tab_conciliacao

        lbl_title = ctk.CTkLabel(frame, text="Processamento Otimizado em Lote", font=ctk.CTkFont(size=18, weight="bold"))
        lbl_title.pack(anchor="w", padx=10, pady=(5, 10))

        client_frame = ctk.CTkFrame(frame)
        client_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(client_frame, text="Cliente:").pack(side="left", padx=10, pady=10)
        self.client_var = ctk.StringVar()
        self.client_dropdown = ctk.CTkOptionMenu(client_frame, variable=self.client_var, values=self._get_client_names(), width=320)
        self.client_dropdown.pack(side="left", padx=10, pady=10)

        btn_reload = ctk.CTkButton(client_frame, text="Atualizar Clientes", width=130, command=self._refresh_clients)
        btn_reload.pack(side="left", padx=5)

        file_frame = ctk.CTkFrame(frame)
        file_frame.pack(fill="x", padx=10, pady=10)

        self.lbl_selected_file = ctk.CTkLabel(file_frame, text="Nenhum arquivo selecionado (OFX, CSV ou PDF)")
        self.lbl_selected_file.pack(side="left", padx=10, pady=10)

        self.selected_file_path = None
        btn_select = ctk.CTkButton(file_frame, text="Selecionar Extrato", command=self._select_file)
        btn_select.pack(side="right", padx=10, pady=10)

        # Barra de Progresso
        prog_frame = ctk.CTkFrame(frame)
        prog_frame.pack(fill="x", padx=10, pady=5)
        self.lbl_prog = ctk.CTkLabel(prog_frame, text="Aguardando início do processamento...", font=ctk.CTkFont(size=12))
        self.lbl_prog.pack(anchor="w", padx=10, pady=(5, 2))
        self.prog_bar = ctk.CTkProgressBar(prog_frame)
        self.prog_bar.pack(fill="x", padx=10, pady=(0, 10))
        self.prog_bar.set(0.0)

        self.btn_process = ctk.CTkButton(
            frame,
            text="Processar em Lote com MAIA",
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._process_statement_flow
        )
        self.btn_process.pack(fill="x", padx=10, pady=10)

        self.txt_log = ctk.CTkTextbox(frame, height=180)
        self.txt_log.pack(fill="both", expand=True, padx=10, pady=5)

    def _get_client_names(self):
        with SessionLocal() as db:
            clients = db.query(Cliente).all()
            return [f"{c.id} - {c.nome}" for c in clients] or ["Nenhum cliente cadastrado"]

    def _refresh_clients(self):
        names = self._get_client_names()
        self.client_dropdown.configure(values=names)
        if names:
            self.client_var.set(names[0])

    def _select_file(self):
        path = filedialog.askopenfilename(filetypes=[("Extratos", "*.ofx;*.csv;*.pdf")])
        if path:
            self.selected_file_path = path
            self.lbl_selected_file.configure(text=os.path.basename(path))

    def _process_statement_flow(self):
        if not self.selected_file_path:
            messagebox.showwarning("Aviso", "Selecione um arquivo de extrato primeiro.")
            return

        client_str = self.client_var.get()
        if " - " not in client_str:
            messagebox.showwarning("Aviso", "Selecione um cliente válido.")
            return

        client_id = int(client_str.split(" - ")[0])
        file_path = self.selected_file_path

        def run_task():
            with SessionLocal() as db:
                try:
                    self.after(0, lambda: self.btn_process.configure(state="disabled"))
                    self._ui_log(f"Lendo e calculando hash SHA-256 de {os.path.basename(file_path)}...")

                    with open(file_path, "rb") as f:
                        content = f.read()

                    ingestion_svc = StatementIngestionService(db)
                    extrato, txs = ingestion_svc.ingest_statement(client_id, os.path.basename(file_path), content)
                    self._ui_log(f"Ingestão em lote concluída: {len(txs)} transações inseridas.")

                    # Classificação em lote com callback de progresso
                    rules_engine = RulesEngineService(db)
                    rules_engine.classify_batch(
                        cliente_id=client_id,
                        transacoes=txs,
                        progress_callback=self._ui_progress
                    )

                    pendentes_ia = [t for t in txs if t.status_revisao == StatusRevisao.PENDENTE]
                    self._ui_log(f"Regras aplicadas. Itens classificados: {len(txs) - len(pendentes_ia)} | Pendentes: {len(pendentes_ia)}")

                    if pendentes_ia:
                        self._ui_log(f"Consultando IA Gemini para {len(pendentes_ia)} itens...")
                        self.ai_classifier.classify_batch(db, client_id, pendentes_ia)

                    client = db.query(Cliente).filter(Cliente.id == client_id).first()
                    out_name = self.spreadsheet_service.get_default_filename(client.nome)
                    save_path = os.path.join(os.path.expanduser("~"), out_name)
                    self.spreadsheet_service.generate_file(txs, save_path, cliente=client)

                    self._ui_log(f"Sucesso! Planilha gerada em:\n{save_path}")
                    self.after(0, lambda: messagebox.showinfo("Sucesso", f"Processamento concluído com sucesso!\nSalvo em: {out_name}"))
                    self.after(0, self._load_pending_review_table)
                    self.after(0, self._load_audit_trail)

                except Exception as e:
                    self._ui_log(f"Erro: {str(e)}")
                    self.after(0, lambda: messagebox.showerror("Erro", str(e)))
                finally:
                    self.after(0, lambda: self.btn_process.configure(state="normal"))

        threading.Thread(target=run_task, daemon=True).start()

    # ==================== ABA 2: REVISÃO ASSISTIDA ====================
    def _setup_revisao_tab(self):
        frame = self.tab_revisao

        top_frame = ctk.CTkFrame(frame)
        top_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(top_frame, text="Revisão Assistida (Clique na linha para preencher o ID)", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left", padx=10)
        btn_refresh = ctk.CTkButton(top_frame, text="Recarregar Pendências", command=self._load_pending_review_table)
        btn_refresh.pack(side="right", padx=10)

        # Resumo
        self.lbl_stats = ctk.CTkLabel(frame, text="Total Pendentes: 0", font=ctk.CTkFont(size=13))
        self.lbl_stats.pack(anchor="w", padx=15, pady=2)

        self.review_box = ctk.CTkTextbox(frame, height=360, font=ctk.CTkFont(family="Courier", size=12))
        self.review_box.pack(fill="both", expand=True, padx=10, pady=5)
        self.review_box.bind("<ButtonRelease-1>", self._on_table_row_click)

        action_frame = ctk.CTkFrame(frame)
        action_frame.pack(fill="x", padx=10, pady=10)

        self.ent_tx_id = ctk.CTkEntry(action_frame, placeholder_text="ID da Transação", width=140)
        self.ent_tx_id.pack(side="left", padx=5)

        self.ent_account_id = ctk.CTkEntry(action_frame, placeholder_text="ID Nova Conta", width=140)
        self.ent_account_id.pack(side="left", padx=5)

        btn_correct = ctk.CTkButton(action_frame, text="Aprovar e Salvar Regra", command=self._apply_correction)
        btn_correct.pack(side="left", padx=10)

    def _on_table_row_click(self, event):
        """Preenche o campo ID com a linha clicada pelo usuário."""
        try:
            line_text = self.review_box.get("insert linestart", "insert lineend").strip()
            parts = [p.strip() for p in line_text.split("|")]
            if parts and parts[0].isdigit():
                self.ent_tx_id.delete(0, "end")
                self.ent_tx_id.insert(0, parts[0])
        except Exception:
            pass

    def _load_pending_review_table(self):
        client_str = self.client_var.get()
        if " - " not in client_str:
            return

        client_id = int(client_str.split(" - ")[0])

        with SessionLocal() as db:
            review_service = ReviewService(db)
            items = review_service.get_pending_review_items(client_id)

            self.lbl_stats.configure(text=f"Total Pendentes: {len(items)}")
            self.review_box.delete("1.0", "end")

            if not items:
                self.review_box.insert("end", "Nenhuma transação pendente de revisão.\n")
                return

            self.review_box.insert("end", f"{'ID':<6} | {'Data':<10} | {'Valor (R$)':<12} | {'Confiança':<10} | {'Histórico Bancário'}\n")
            self.review_box.insert("end", "=" * 90 + "\n")
            for it in items:
                self.review_box.insert("end", f"{it.id:<6} | {it.data.strftime('%d/%m/%Y')} | {it.valor:<12.2f} | {it.nivel_confianca:<10} | {it.descricao_banco}\n")

    def _apply_correction(self):
        tx_id_str = self.ent_tx_id.get().strip()
        acc_id_str = self.ent_account_id.get().strip()

        if not tx_id_str or not acc_id_str:
            messagebox.showwarning("Aviso", "Preencha o ID da Transação e o ID da Conta.")
            return

        with SessionLocal() as db:
            try:
                review_service = ReviewService(db)
                req = ManualCorrectionRequest(
                    transacao_id=int(tx_id_str),
                    nova_conta_id=int(acc_id_str),
                    salvar_como_regra=True
                )
                review_service.correct_manually(req)
                messagebox.showinfo("Sucesso", "Transação aprovada e regra permanente gerada no MAIA!")
                self._load_pending_review_table()
                self._load_audit_trail()
                self.ent_tx_id.delete(0, "end")
                self.ent_account_id.delete(0, "end")
            except Exception as e:
                messagebox.showerror("Erro", str(e))

    # ==================== ABA 3: AUDITORIA ====================
    def _setup_auditoria_tab(self):
        frame = self.tab_auditoria

        top_frame = ctk.CTkFrame(frame)
        top_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(top_frame, text="Trilha Imutável de Auditoria Contábil", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=10)
        btn_refresh = ctk.CTkButton(top_frame, text="Atualizar Log", command=self._load_audit_trail)
        btn_refresh.pack(side="right", padx=10)

        self.audit_box = ctk.CTkTextbox(frame, height=450, font=ctk.CTkFont(family="Courier", size=11))
        self.audit_box.pack(fill="both", expand=True, padx=10, pady=5)
        self.audit_box.insert("end", "Clique em 'Atualizar Log' para carregar a trilha de auditoria.\n")

    def _load_audit_trail(self):
        with SessionLocal() as db:
            logs = db.query(LogAuditoria).order_by(LogAuditoria.created_at.desc()).limit(100).all()
            self.audit_box.delete("1.0", "end")
            if not logs:
                self.audit_box.insert("end", "Nenhum registro de auditoria no histórico.\n")
                return

            self.audit_box.insert("end", f"{'Data/Hora':<20} | {'Tx ID':<8} | {'Ação':<20} | {'Usuário':<12} | {'Detalhes'}\n")
            self.audit_box.insert("end", "=" * 95 + "\n")
            for log in logs:
                dt_str = log.created_at.strftime('%d/%m/%Y %H:%M:%S')
                self.audit_box.insert("end", f"{dt_str:<20} | {log.transacao_id:<8} | {log.acao:<20} | {log.usuario:<12} | {log.detalhes or ''}\n")

    # ==================== ABA 4: AÇÕES & CVM ====================
    def _setup_acoes_tab(self):
        frame = self.tab_acoes

        top_frame = ctk.CTkFrame(frame)
        top_frame.pack(fill="x", padx=10, pady=10)

        self.ent_stock_search = ctk.CTkEntry(top_frame, placeholder_text="Digite Ticker ou Nome (ex: PETR4, VALE3, ITUB4)", width=450)
        self.ent_stock_search.pack(side="left", padx=10, pady=10)

        btn_search = ctk.CTkButton(top_frame, text="Consultar", command=self._search_stock)
        btn_search.pack(side="left", padx=10, pady=10)

        self.txt_stock_result = ctk.CTkTextbox(frame, height=400)
        self.txt_stock_result.pack(fill="both", expand=True, padx=10, pady=5)

    def _search_stock(self):
        term = self.ent_stock_search.get().strip()
        if not term:
            return

        self.txt_stock_result.delete("1.0", "end")
        self.txt_stock_result.insert("end", f"Buscando cotação e CNPJ oficial para '{term}'...\n\n")

        def run_search():
            try:
                res = self.stocks_service.search_by_name_or_ticker(term)
                
                def update_ui():
                    self.txt_stock_result.delete("1.0", "end")
                    if not res.resultados:
                        self.txt_stock_result.insert("end", f"Nenhum ativo localizado para '{term}'.\n")
                        return

                    for q in res.resultados:
                        self.txt_stock_result.insert("end", f"Ticker: {q.ticker}\n")
                        self.txt_stock_result.insert("end", f"Razão Social: {q.nome_empresa}\n")
                        self.txt_stock_result.insert("end", f"CNPJ CVM: {q.cnpj or 'Não localizado'}\n")
                        self.txt_stock_result.insert("end", f"Preço Atual: R$ {q.preco_atual:.2f}\n")
                        self.txt_stock_result.insert("end", f"Variação Dia: {q.variacao_dia}%\n")
                        self.txt_stock_result.insert("end", "-" * 60 + "\n\n")

                self.after(0, update_ui)
            except Exception as e:
                self.after(0, lambda: self.txt_stock_result.insert("end", f"Erro: {str(e)}\n"))

        threading.Thread(target=run_search, daemon=True).start()

    # ==================== ABA 5: NUVEM & CONFIG ====================
    def _setup_config_tab(self):
        frame = self.tab_config

        lbl_info = ctk.CTkLabel(frame, text="Integrações em Nuvem com Armazenamento Idempotente", font=ctk.CTkFont(size=16, weight="bold"))
        lbl_info.pack(anchor="w", padx=15, pady=15)

        gdrive_card = ctk.CTkFrame(frame)
        gdrive_card.pack(fill="x", padx=15, pady=10)
        ctk.CTkLabel(gdrive_card, text="Google Drive: Escopo restrito 'drive.file' configurado").pack(side="left", padx=15, pady=15)
        ctk.CTkButton(gdrive_card, text="Status: Ativo", state="disabled", width=120).pack(side="right", padx=15)

        onedrive_card = ctk.CTkFrame(frame)
        onedrive_card.pack(fill="x", padx=15, pady=10)
        ctk.CTkLabel(onedrive_card, text="Microsoft OneDrive: Graph API OAuth 2.0 configurado").pack(side="left", padx=15, pady=15)
        ctk.CTkButton(onedrive_card, text="Status: Ativo", state="disabled", width=120).pack(side="right", padx=15)


def launch():
    app = MaiaApp()
    app.mainloop()


if __name__ == "__main__":
    launch()