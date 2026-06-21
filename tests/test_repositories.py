import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, r'C:\Users\faishaltsq\Documents\Kerjaan\Things that i want to build\OneTapTrade\ai-trading-executor')


def test_update_bot_settings_allows_risk_profile():
    from app.database.repositories import update_bot_settings

    table = MagicMock()
    table.update.return_value = table
    table.eq.return_value = table
    table.execute.return_value = MagicMock(data=[{"id": "row-1", "risk_profile": "HIGH"}])

    supabase = MagicMock()
    supabase.table.return_value = table

    with patch("app.database.repositories.get_supabase", return_value=supabase):
        with patch("app.database.repositories.get_bot_settings", return_value={"id": "row-1"}):
            result = update_bot_settings({"risk_profile": "HIGH"})

    table.update.assert_called_once_with({"risk_profile": "HIGH"})
    assert result["risk_profile"] == "HIGH"


def test_update_bot_settings_retries_without_missing_schema_column():
    from app.database.repositories import update_bot_settings

    table = MagicMock()
    table.eq.return_value = table

    first_execute = table.execute
    first_execute.side_effect = [
        Exception("{'message': \"Could not find the 'risk_profile' column of 'bot_settings' in the schema cache\", 'code': 'PGRST204'}"),
        MagicMock(data=[{"id": "row-1", "risk_per_trade_percent": 1.0}]),
    ]
    table.update.return_value = table

    supabase = MagicMock()
    supabase.table.return_value = table

    with patch("app.database.repositories.get_supabase", return_value=supabase):
        with patch("app.database.repositories.get_bot_settings", return_value={"id": "row-1"}):
            result = update_bot_settings({"risk_profile": "HIGH", "risk_per_trade_percent": 1.0})

    assert table.update.call_args_list[0].args[0] == {"risk_profile": "HIGH", "risk_per_trade_percent": 1.0}
    assert table.update.call_args_list[1].args[0] == {"risk_per_trade_percent": 1.0}
    assert result["risk_per_trade_percent"] == 1.0


def test_update_bot_settings_accepts_strategy_mode():
    from unittest.mock import patch, MagicMock

    with patch("app.database.repositories.get_supabase") as mock_get:
        mock_client = MagicMock()
        mock_get.return_value = mock_client

        mock_client.table.return_value.select.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "test-id"}])
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "test-id", "strategy_mode": "AI_ONLY"}])

        from app.database.repositories import update_bot_settings

        result = update_bot_settings({"strategy_mode": "AI_ONLY"})

        assert result is not None
        assert result["strategy_mode"] == "AI_ONLY"
