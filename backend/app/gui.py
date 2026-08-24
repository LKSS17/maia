"""Interface Desktop do MAIA desenvolvida com CustomTkinter."""

import os
import threading
from tkinter import filedialog, messagebox
import customtkinter as ctk

from backend.app.db.session import SessionLocal, Base, engine
from backend.app.models.entities import Cliente, PlanoContas
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
        self.geometry("980x680")
        self.minsize(850, 550)

        # Inicializar banco de dados local automaticamente
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()

        self.spreadsheet_service = SpreadsheetGeneratorService()
        self.stocks_service = StocksService()
        self.review_service = ReviewService(self.db)

        # Layout Principal com Abas
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=15)

        self.tab_conciliacao = self.tabview.add("📂 Conciliação Bancária")
        self.tab_revisao = self.tabview.add("🔍 Revisão de Lançamentos")
        self.tab_acoes = self.tabview.add("📈 Consulta de Ações")
        self.tab_config = self.tabview.add("⚙️ Configurações & Nuvem")

        self._setup_conciliacao_tab()
        self._setup_revisao_tab()
        self._setup_acoes_tab()
        self._setup_config_tab()

    # ==================== ABA 1: CONCILIAÇÃO ====================
    def _setup_conciliacao_tab(self):
        frame = self.tab_conciliacao

        lbl_title = ctk.CTkLabel(frame, text="Processamento de Extratos Bancários", font=ctk.CTkFont(size=18, weight="bold"))
        lbl_title.pack(anchor="w", padx=10, pady=(5, 15))

        # Seleção de Cliente
        client_frame = ctk.CTkFrame(frame)
        client_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(client_frame, text="Cliente:").pack(side="left", padx=10, pady=10)
        self.client_var = ctk.StringVar()
        self.client_dropdown = ctk.CTkOptionMenu(client_frame, variable=self.client_var, values=self._get_client_names(), width=300)
        self.client_dropdown.pack(side="left", padx=10, pady=10)

        btn_reload = ctk.CTkButton(client_frame, text="Atualizar Lista", width=120, command=self._refresh_clients)
        btn_reload.pack(side="left", padx=5)

        # Upload e Arquivo
        file_frame = ctk.CTkFrame(frame)
        file_frame.pack(fill="x", padx=10, pady=10)

        self.lbl_selected_file = ctk.CTkLabel(file_frame, text="Nenhum arquivo selecionado (OFX, CSV ou PDF)")
        self.lbl_selected_file.pack(side="left", padx=10, pady=10)

        self.selected_file_path = None
        btn_select = ctk.CTkButton(file_frame, text="Selecionar Extrato", command=self._select_file)
        btn_select.pack(side="right", padx=10, pady=10)

        # Ação Principal
        self.btn_process = ctk.CTkButton(
            frame,
            text="Processar e Classificar com MAIA",
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._process_statement_flow
        )
        self.btn_process.pack(fill="x", padx=10, pady=15)

        # Log visual de status
        self.txt_log = ctk.CTkTextbox(frame, height=220)
        self.txt_log.pack(fill="both", expand=True, padx=10, pady=5)
        self.txt_log.insert("end", "Pronto para processar extratos.\n")

    def _get_client_names(self):
        clients = self.db.query(Cliente).all()
        return [f"{c.id} - {c.nome}" for c in clients] or ["Nenhum cliente cadastrado"]

    def _refresh_clients(self):
        names = self._get_client_names()
        self.client_dropdown.configure(values=names)
        if names:
            self.client_var.set(names[0])

    def _select_file(self):
        path = filedialog.askopenfilename(filetypes=[("Extratos Suportados", "*.ofx;*.csv;*.pdf")])
        if path:
            self.selected_file_path = path
            self.lbl_selected_file.configure(text=os.path.basename(path))

    def _log(self, text: str):
        self.txt_log.insert("end", text + "\n")
        self.txt_log.see("end")

    def _process_statement_flow(self):
        if not self.selected_file_path:
            messagebox.showwarning("Aviso", "Por favor, selecione um arquivo de extrato primeiro.")
            return

        client_str = self.client_var.get()
        if " - " not in client_str:
            messagebox.showwarning("Aviso", "Selecione um cliente válido.")
            return

        client_id = int(client_str.split(" - ")[0])

        def run_task():
            try:
                self.btn_process.configure(state="disabled")
                self._log(f"Iniciando leitura de {os.path.basename(self.selected_file_path)}...")

                with open(self.selected_file_path, "rb") as f:
                    content = f.read()

                # Ingestão
                ingestion_svc = StatementIngestionService(self.db)
                extrato, txs = ingestion_svc.ingest_statement(client_id, os.path.basename(self.selected_file_path), content)
                self._log(f"Ingestão concluída: {len(txs)} transações importadas.")

                # Regras
                rules_engine = RulesEngineService(self.db)
                pendentes_ia = []
                for t in txs:
                    rules_engine.classify_transaction(t)
                    if t.status_revisao.value == "pendente":
                        pendentes_ia.append(t)

                self._log(f"Cascata de Regras aplicada. {len(txs) - len(pendentes_ia)} itens classificados.")

                # IA Gemini para residuais
                if pendentes_ia:
                    self._log(f"Consultando IA para {len(pendentes_ia)} transações residuais...")
                    gemini_svc = GeminiClassifierService(self.db)
                    gemini_svc.classify_batch(client_id, pendentes_ia)

                # Gerar Planilha
                client = self.db.query(Cliente).filter(Cliente.id == client_id).first()
                out_name = self.spreadsheet_service.get_default_filename(client.nome)
                save_path = os.path.join(os.path.expanduser("~"), out_name)
                self.spreadsheet_service.generate_file(txs, save_path, client=client)

                self._log(f"Planilha de conciliação gerada com sucesso em:\n{save_path}")
                messagebox.showinfo("Sucesso", f"Processamento concluído!\nPlanilha gerada: {out_name}")
                self._load_pending_review_table()

            except Exception as e:
                self._log(f"Erro durante o processamento: {str(e)}")
                messagebox.showerror("Erro", f"Não foi possível concluir o processamento:\n{str(e)}")
            finally:
                self.btn_process.configure(state="normal")

        threading.Thread(target=run_task, daemon=True).start()

    # ==================== ABA 2: REVISÃO ====================
    def _setup_revisao_tab(self):
        frame = self.tab_revisao

        top_frame = ctk.CTkFrame(frame)
        top_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(top_frame, text="Revisão de Lançamentos Pendentes / Baixa Confiança", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=10)
        btn_refresh = ctk.CTkButton(top_frame, text="Carregar Pendências", command=self._load_pending_review_table)
        btn_refresh.pack(side="right", padx=10)

        self.review_box = ctk.CTkTextbox(frame, height=380)
        self.review_box.pack(fill="both", expand=True, padx=10, pady=5)

        action_frame = ctk.CTkFrame(frame)
        action_frame.pack(fill="x", padx=10, pady=10)

        self.ent_tx_id = ctk.CTkEntry(action_frame, placeholder_text="ID da Transação", width=120)
        self.ent_tx_id.pack(side="left", padx=5)

        self.ent_account_id = ctk.CTkEntry(action_frame, placeholder_text="ID Nova Conta", width=120)
        self.ent_account_id.pack(side="left", padx=5)

        btn_correct = ctk.CTkButton(action_frame, text="Aprovar / Corrigir e Salvar Regra", command=self._apply_correction)
        btn_correct.pack(side="left", padx=10)

    def _load_pending_review_table(self):
        client_str = self.client_var.get()
        if " - " not in client_str:
            return

        client_id = int(client_str.split(" - ")[0])
        items = self.review_service.get_pending_review_items(client_id)

        self.review_box.delete("1.0", "end")
        if not items:
            self.review_box.insert("end", "Nenhuma transação pendente de revisão para este cliente.\n")
            return

        self.review_box.insert("end", f"{'ID':<6} | {'Data':<10} | {'Valor (R$)':<12} | {'Confiança':<10} | {'Histórico Bancário'}\n")
        self.review_box.insert("end", "-" * 85 + "\n")
        for it in items:
            self.review_box.insert("end", f"{it.id:<6} | {it.data.strftime('%d/%m/%Y')} | {it.valor:<12.2f} | {it.nivel_confianca:<10} | {it.descricao_banco}\n")

    def _apply_correction(self):
        tx_id_str = self.ent_tx_id.get().strip()
        acc_id_str = self.ent_account_id.get().strip()

        if not tx_id_str or not acc_id_str:
            messagebox.showwarning("Aviso", "Preencha o ID da Transação e o ID da Conta.")
            return

        try:
            req = ManualCorrectionRequest(
                transacao_id=int(tx_id_str),
                nova_conta_id=int(acc_id_str),
                salvar_como_regra=True
            )
            self.review_service.correct_manually(req)
            messagebox.showinfo("Sucesso", "Transação revisada e nova regra aprendida pelo MAIA!")
            self._load_pending_review_table()
            self.ent_tx_id.delete(0, "end")
            self.ent_account_id.delete(0, "end")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha na revisão: {str(e)}")

    # ==================== ABA 3: CONSULTA DE AÇÕES ====================
    def _setup_acoes_tab(self):
        frame = self.tab_acoes

        top_frame = ctk.CTkFrame(frame)
        top_frame.pack(fill="x", padx=10, pady=10)

        self.ent_stock_search = ctk.CTkEntry(top_frame, placeholder_text="Digite o Nome da Empresa ou Ticker (ex: Petrobras, VALE3, ITUB4)", width=450)
        self.ent_stock_search.pack(side="left", padx=10, pady=10)

        btn_search = ctk.CTkButton(top_frame, text="Consultar Ação", command=self._search_stock)
        btn_search.pack(side="left", padx=10, pady=10)

        self.txt_stock_result = ctk.CTkTextbox(frame, height=400)
        self.txt_stock_result.pack(fill="both", expand=True, padx=10, pady=5)
        self.txt_stock_result.insert("end", "Digite um nome de companhia ou ticker para obter cotação e CNPJ CVM.\n")

    def _search_stock(self):
        term = self.ent_stock_search.get().strip()
        if not term:
            return

        self.txt_stock_result.delete("1.0", "end")
        self.txt_stock_result.insert("end", f"Buscando informações para '{term}'...\n\n")

        def run_search():
            try:
                res = self.stocks_service.search_by_name_or_ticker(term)
                self.txt_stock_result.delete("1.0", "end")
                if not res.resultados:
                    self.txt_stock_result.insert("end", f"Nenhuma cotação encontrada para '{term}'.\n")
                    return

                for q in res.resultados:
                    self.txt_stock_result.insert("end", f"Ticker: {q.ticker}\n")
                    self.txt_stock_result.insert("end", f"Empresa: {q.nome_empresa}\n")
                    self.txt_stock_result.insert("end", f"CNPJ Oficial (CVM): {q.cnpj or 'Não mapeado'}\n")
                    self.txt_stock_result.insert("end", f"Preço Atual: R$ {q.preco_atual:.2f}\n")
                    self.txt_stock_result.insert("end", f"Variação Dia: {q.variacao_dia}%\n")
                    self.txt_stock_result.insert("end", f"Data/Hora Consulta: {q.data_hora_consulta.strftime('%d/%m/%Y %H:%M:%S')}\n")
                    self.txt_stock_result.insert("end", "-" * 60 + "\n\n")
            except Exception as e:
                self.txt_stock_result.insert("end", f"Erro na consulta: {str(e)}\n")

        threading.Thread(target=run_search, daemon=True).start()

    # ==================== ABA 4: NUVEM & CONFIG ====================
    def _setup_config_tab(self):
        frame = self.tab_config

        lbl_info = ctk.CTkLabel(frame, text="Integrações em Nuvem (Google Drive & Microsoft OneDrive)", font=ctk.CTkFont(size=16, weight="bold"))
        lbl_info.pack(anchor="w", padx=15, pady=15)

        gdrive_card = ctk.CTkFrame(frame)
        gdrive_card.pack(fill="x", padx=15, pady=10)
        ctk.CTkLabel(gdrive_card, text="Google Drive: Escopo restrito (drive.file) configurado").pack(side="left", padx=15, pady=15)
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
