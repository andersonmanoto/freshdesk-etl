# Mapeia custom field do Freshdesk → (tabela Supabase, coluna de upsert)
FIELD_TO_LOOKUP_TABLE: dict[str, tuple[str, str]] = {
    "cf_motivo_da_solicitao": ("cs_cancellation_reasons", "reason"),
    "cf_degrau_aplicado":     ("cs_retention_steps",      "step_name"),
}