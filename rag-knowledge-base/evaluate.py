"""
evaluate.py —— 参数对比实验（项目亮点）
准备 20 个问答对，跑三组参数：chunk_size / chunk_overlap / top_k。
输出 results/evaluation.csv + 参数对比图（面试亮证据）。
"""
import os
import csv
import time
import argparse
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config
from ingest import build
from retrieve import answer

# 20 个问答对模板（请按你的语料替换为真实问题与标准答案关键词）
# 格式: (问题, [答案中应包含的关键词...])
QA_PAIRS = [
    ("MySQL 8 默认的认证插件是什么？", ["caching_sha2_password"]),
    ("怎么查看当前的 binlog 是否开启？", ["log_bin", "ON"]),
    ("mysqldump 做全量备份为什么要加 --single-transaction？", ["不锁表", "一致性"]),
    ("XtraBackup 增量 prepare 为什么要 --apply-log-only？", ["跳过回滚", "增量"]),
    ("主从复制双 Yes 指哪两个线程？", ["IO", "SQL", "Yes"]),
    (" Seconds_Behind_Source 为 NULL 说明什么？", ["未运行", "NULL"]),
    ("GTID 自动定位用哪个参数？", ["SOURCE_AUTO_POSITION", "1"]),
    ("半同步复制主库哪个状态变量表示已连接从库数？", ["Rpl_semi_sync_source_clients"]),
    ("慢查询 EXPLAIN 中 type=ALL 代表什么？", ["全表扫描"]),
    ("函数包裹列为会导致索引失效吗？", ["失效", "函数"]),
    ("前缀索引的 SQL 语法怎么写？", ["pad(20)", "INDEX"]),
    ("死锁报错的 ERROR 编号是多少？", ["1213"]),
    ("innodb_trx 表里哪个字段是阻塞源线程号？", ["trx_mysql_thread_id"]),
    ("KILL 掉阻塞源后锁等待会怎样？", ["释放", "Query OK"]),
    ("磁盘写满 MySQL 报什么错？", ["No space left", "1030"]),
    ("连接数打满报什么错？", ["Too many connections", "1040"]),
    ("怎么设置 binlog 自动过期 7 天？", ["binlog_expire_logs_seconds", "604800"]),
    ("PITR 恢复时 --stop-position 取哪个位点？", ["DROP", "end_log_pos"]),
    ("root 密码忘了怎么在 CentOS 上重置？", ["skip-grant-tables", "ALTER USER"]),
    ("MySQL 8 与 5.7 用户授权语法的区别？", ["GRANT", "IDENTIFIED", "不能同时"]),
]


def evaluate(chunk_size, chunk_overlap, top_k, tag, with_llm=False, limit=None):
    """跑一组参数，返回命中率/准确率/索引耗时/延迟。limit 用于 --quick 只跑前 N 题。"""
    db_dir = f"{config.DB_DIR}_{tag}"
    t0 = time.time()
    build(chunk_size, chunk_overlap, db_dir, rebuild=True)
    index_time = round(time.time() - t0, 2)

    qa_pairs = QA_PAIRS[:limit] if limit else QA_PAIRS
    hit = correct = 0
    latencies = []
    for q, keywords in qa_pairs:
        r = answer(q, db_dir=db_dir, top_k=top_k, with_llm=with_llm)
        context = " ".join(s["snippet"] for s in r["sources"]).lower()
        if any(k.lower() in context for k in keywords):
            hit += 1
        if with_llm and r.get("answer") and any(k.lower() in r["answer"].lower() for k in keywords):
            correct += 1
        if r.get("latency"):
            latencies.append(r["latency"])

    avg_latency = round(sum(latencies) / len(latencies), 3) if latencies else None
    return {
        "group": tag,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "top_k": top_k,
        "hit_rate": round(hit / len(qa_pairs), 3),
        "accuracy": round(correct / len(qa_pairs), 3) if with_llm else "N/A(未调LLM)",
        "index_time_s": index_time,
        "avg_latency_s": avg_latency if avg_latency is not None else "N/A",
    }


def plot(results):
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    df = pd.DataFrame(results)
    # 三组对比图：命中率 vs 各参数
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    for ax, (col, title) in zip(axes, [("chunk_size", "chunk_size"),
                                       ("chunk_overlap", "chunk_overlap"),
                                       ("top_k", "top_k")]):
        g = df.groupby(col)["hit_rate"].mean()
        ax.bar([str(x) for x in g.index], g.values, color="#4C78A8")
        ax.set_title(f"命中率 vs {title}")
        ax.set_ylabel("命中率")
        ax.set_ylim(0, 1.05)
        for i, v in enumerate(g.values):
            ax.text(i, v + 0.02, f"{v:.2f}", ha="center")
    plt.tight_layout()
    out = os.path.join(config.RESULTS_DIR, "param_compare.png")
    plt.savefig(out, dpi=150)
    print(f"对比图已保存: {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-llm", action="store_true", help="是否调用 LLM 测准确率（需 key/Ollama，慢）")
    ap.add_argument("--quick", action="store_true", help="快速模式：每组只跑 5 题，先验证流程")
    args = ap.parse_args()

    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    results = []

    groups = [
        ("cs256", 256, config.CHUNK_OVERLAP, config.TOP_K),
        ("cs512", 512, config.CHUNK_OVERLAP, config.TOP_K),
        ("cs1024", 1024, config.CHUNK_OVERLAP, config.TOP_K),
        ("ov0", config.CHUNK_SIZE, 0, config.TOP_K),
        ("ov100", config.CHUNK_SIZE, 100, config.TOP_K),
        ("ov200", config.CHUNK_SIZE, 200, config.TOP_K),
        ("tk3", config.CHUNK_SIZE, config.CHUNK_OVERLAP, 3),
        ("tk5", config.CHUNK_SIZE, config.CHUNK_OVERLAP, 5),
        ("tk10", config.CHUNK_SIZE, config.CHUNK_OVERLAP, 10),
    ]
    if args.quick:
        # 快速验证：只跑 chunk_size 的 3 组，每组前 5 题，先确认流程能跑通
        groups = groups[:3]
        print("[quick] 快速模式：仅跑 3 组 × 5 题，用于验证流程")
    for tag, cs, ov, tk in groups:
        print(f"\n>>> 跑参数组 {tag}: chunk_size={cs} overlap={ov} top_k={tk}")
        r = evaluate(cs, ov, tk, tag, with_llm=args.with_llm, limit=5 if args.quick else None)
        results.append(r)
        print(r)

    csv_path = os.path.join(config.RESULTS_DIR, "evaluation.csv")
    pd.DataFrame(results).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n结果表已保存: {csv_path}")
    plot(results)
