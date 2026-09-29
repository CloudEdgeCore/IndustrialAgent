-- 容器首次初始化时的扩展兜底（正常由迁移/P1 管理）
CREATE EXTENSION IF NOT EXISTS timescaledb;

DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'pgvector extension not available in this image: %', SQLERRM;
END;
$$;
