"""RAG 关键词臂 SQL 构造单元测试（无需数据库）。

回归点：关键词臂原先 **没有 ORDER BY**，`LIMIT` 截取的是堆序行，
RRF 融合因此引入噪声。此测试锁定"相关度排序 + 确定性"这一契约。
"""

from tools.rag.search import KEYWORD_TOP_K, _keyword_params, _keyword_sql, _keyword_tokens


def test_keyword_sql_orders_by_relevance() -> None:
    sql_text = _keyword_sql(["裂纹", "主轴"], [])
    assert "ORDER BY" in sql_text, "关键词臂必须有 ORDER BY，否则 LIMIT 截取堆序行"
    assert sql_text.index("ORDER BY") < sql_text.index("LIMIT")
    assert "DESC" in sql_text


def test_keyword_sql_is_deterministic_with_id_tiebreaker() -> None:
    sql_text = _keyword_sql(["裂纹"], [])
    assert "c.id ASC" in sql_text, "需要确定性兜底，避免同分时顺序随机"


def test_keyword_sql_parameterizes_tokens() -> None:
    sql_text = _keyword_sql(["裂纹", "主轴"], [])
    assert "ILIKE %s" in sql_text
    assert "裂纹" not in sql_text, "token 必须参数化，不得内联进 SQL"
    assert "主轴" not in sql_text


def test_keyword_params_match_placeholder_count() -> None:
    tokens = ["裂纹", "主轴", "温度"]
    filters = ["d.document_type = %s", "d.equipment_type = %s"]
    sql_text = _keyword_sql(tokens, filters)
    params = _keyword_params(tokens, ["manual", "cnc"], 20)
    # 占位符 = WHERE token×n + filters×m + ORDER BY token×n + LIMIT
    assert sql_text.count("%s") == len(tokens) * 2 + len(filters) + 1
    assert len(params) == sql_text.count("%s")


def test_keyword_params_order_is_where_then_order() -> None:
    params = _keyword_params(["a", "b"], ["F"], 7)
    # WHERE 两个 pattern → filter → ORDER BY 两个 pattern → LIMIT
    assert params == ("%a%", "%b%", "F", "%a%", "%b%", 7)


def test_keyword_params_without_filters() -> None:
    params = _keyword_params(["a"], [], KEYWORD_TOP_K)
    assert params == ("%a%", "%a%", KEYWORD_TOP_K)


def test_keyword_tokens_drops_short_and_stopword_tokens() -> None:
    tokens = _keyword_tokens("E102 的温度怎么处理")
    assert "e102" in tokens or "E102" in tokens
    assert all(len(token) >= 2 for token in tokens), "单字符 token 不应进入 ILIKE"
    assert "的" not in tokens
    assert "怎么" not in tokens
