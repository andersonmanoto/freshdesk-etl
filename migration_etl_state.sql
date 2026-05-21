-- Tabela de controle de estado do ETL
-- Roda uma vez no Supabase antes do primeiro deploy

CREATE TABLE IF NOT EXISTS etl_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Trigger para atualizar updated_at automaticamente
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER etl_state_updated_at
    BEFORE UPDATE ON etl_state
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
