"""
Supabase table schemas reference.

Tables (defined in supabase/schema.sql):

- bot_settings     : system-wide configuration row
- market_snapshots : OHLC + technical/orderflow payloads per symbol/timeframe
- ai_decisions     : LLM decision output linked to a market snapshot
- risk_checks      : risk gate result tied to an ai_decision
- trades           : executed or pending trade records
- telegram_commands: inbound telegram command audit log
- bot_events       : operational event log

Column definitions are maintained in the schema.sql migration file.
"""
