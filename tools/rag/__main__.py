"""CLI：python -m tools.rag ingest | search "<query>"。"""

import argparse
import json

from tools.rag.ingest import ingest_documents
from tools.rag.search import search


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 工具（文档导入 / 检索调试）")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ingest", help="导入 data/fixtures/knowledge 下的全部文档")

    search_parser = sub.add_parser("search", help="检索调试")
    search_parser.add_argument("query")
    search_parser.add_argument("--top-k", type=int, default=5)

    args = parser.parse_args()

    if args.command == "ingest":
        summary = ingest_documents()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        results = search(args.query, top_k=args.top_k)
        for index, item in enumerate(results, start=1):
            print(
                f"{index}. [{item['scores']['rerank']:.4f}] "
                f"{item['document_title']} §{item['section']} "
                f"(chunk #{item['chunk_index']})"
            )
            print(f"   {item['content'][:120]}...")


if __name__ == "__main__":
    main()
