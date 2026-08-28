"""Databricks SQL warehouse access for AI SQL functions (e.g. ai_translate).

Lakebase is plain Postgres and has no `ai_translate`, so translation runs on the
serverless SQL warehouse via the Statement Execution API (parameter-bound, using
the app service principal's token).
"""

from __future__ import annotations

from databricks.sdk.service.sql import StatementParameterListItem

from . import config


def ai_translate(text: str, target_lang: str) -> str:
    """Translate `text` into `target_lang` (a language code like 'es') via ai_translate."""
    client = config.get_workspace_client()
    resp = client.statement_execution.execute_statement(
        warehouse_id=config.WAREHOUSE_ID,
        statement="select ai_translate(:t, :l) as translated",
        parameters=[
            StatementParameterListItem(name="t", value=text),
            StatementParameterListItem(name="l", value=target_lang),
        ],
        wait_timeout="30s",
    )
    state = resp.status.state.value if resp.status and resp.status.state else "UNKNOWN"
    if state != "SUCCEEDED":
        msg = resp.status.error.message if (resp.status and resp.status.error) else state
        raise RuntimeError(f"ai_translate failed: {msg}")
    data = resp.result.data_array if resp.result else None
    return data[0][0] if data and data[0] else ""
