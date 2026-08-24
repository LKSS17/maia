# 🏛️ MAIA — Motor de Análise e Inteligência Contábil

**Sistema de Automação Contábil, Classificação Inteligente de Extratos e Auditoria Financeira.**

---

## 📌 Sobre o Projeto
O **MAIA** é um motor de inteligência e automação desenvolvido para contadores autônomos e escritórios contábeis. O sistema resolve o gargalo operacional de leitura, validação e conciliação de extratos bancários brutos, classificando lançamentos com regras contábeis em cascata, autoaprendizado contínuo e inferência residual via IA (Google Gemini API).

---

## 🏗️ Arquitetura do Sistema

```text
               ┌────────────────────────────────────────────────────────┐
               │              Extrato (OFX / CSV / PDF)                 │
               └──────────────────────────┬─────────────────────────────┘
                                          │
                           [ Deduplicação Hash SHA-256 ]
                                          │
                                          ▼
           ┌────────────────────────────────────────────────────────────┐
           │                   CASCATA DE CLASSIFICAÇÃO                 │
           │                                                            │
           │  1. Camada 1: Regras Exatas & Histórico (CNPJ/Texto)      │
           │  2. Camada 2: Regras Contábeis Semânticas                  │
           │  3. Camada 3: Gemini LLM (Lote residual com Rate Limit)    │
           └──────────────────────────┬─────────────────────────────────┘
                                      │
                     ┌────────────────┴────────────────┐
                     ▼                                 ▼
         [ Classificado com Sucesso ]       [ Baixa Confiança / Dúvida ]
                     │                                 │
                     ▼                                 ▼
         ┌───────────────────────┐         ┌───────────────────────┐
         │ Planilha XLSX Oficial │         │ Revisão Human-in-Loop │
         │  (openpyxl formatado) │         │ (Gera Regra Camada 1) │
         └───────────────────────┘         └───────────────────────┘