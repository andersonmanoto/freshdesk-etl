# Freshdesk ETL → Supabase

## Estrutura

```
freshdesk_etl/
├── main.py                  # Ponto de entrada, orquestra o pipeline
├── config/
│   ├── __init__.py
│   └── settings.py          # Configurações via pydantic-settings (.env)
├── services/
│   ├── __init__.py
│   ├── freshdesk.py         # Client HTTP para a API do Freshdesk
│   └── supabase_client.py   # Instância singleton do client Supabase
├── steps/
│   ├── __init__.py
│   ├── extract.py           # E — busca tickets + agentes no Freshdesk
│   ├── enrich.py            # E — cruza tickets com dados de vendas
│   ├── transform.py         # T — normaliza e monta payload Supabase
│   └── load.py              # L — upsert em chunks + controle de estado
└── utils/
    ├── __init__.py
    └── logger.py            # Configuração Loguru
```

## Setup

```bash
pip install requests python-dateutil supabase pydantic-settings loguru tenacity
cp .env.example .env
# preencher .env com as credenciais reais
python main.py
```

## Variáveis de ambiente (.env)

```
FD_DOMAIN=seu-dominio
FD_API_KEY=sua-api-key
SUPA_URL=https://xxx.supabase.co
SUPA_KEY=eyJ...
```
