# dba-portfolio
MySQL 运维实操 + 故障案例复盘 + RAG 知识库实践

# DBA 学习与实战实验仓库

> MySQL 运维实操 + 故障案例复盘 + RAG 知识库实践
> 所有实验均在本人虚拟机环境真实执行，附完整命令、截图与结果。

## 目录
- `mysql-ops/00-environment/` 环境与安装
- `mysql-ops/02-user-privilege/` 用户与权限
- `mysql-ops/03-pitr/` binlog 与按时间点恢复（PITR）
- `mysql-ops/04-xtrabackup/` XtraBackup 全量 + 增量备份恢复
- `mysql-ops/05-replication/` 主从复制（GTID / 延迟 / 半同步）
- `mysql-ops/06-slow-query/` 慢查询定位与优化（sysbench + EXPLAIN）
- `mysql-ops/07-lock-deadlock/` 锁等待与死锁排查
- `notes/` 故障复盘笔记（8 篇）
- `scripts/check_mysql.sh` MySQL 监控脚本（磁盘/连接数/慢查询阈值告警）
- `rag-knowledge-base/` RAG 私有知识库（骨架已就绪，待补 API key 与参数实验）

## 环境
VMware Workstation + CentOS 7 + MySQL 8.0；Percona XtraBackup 8.0；Python 3.10 + LangChain

## 亮点结果
- **慢查询优化**：EXPLAIN `type` 由 `ALL` → `range`，扫描行数 986400 → 1，实际耗时 **512ms → 0.0135ms**（sysbench 400 万行数据集）
- **压测基线**：8 线程 60 秒，TPS 467 / QPS 9345 / 95% 延迟 30.26ms
- **备份恢复**：mysqldump + binlog PITR、XtraBackup 全量 + 增量恢复均已验证
- **主从复制**：GTID 自动定位 + 延迟演练 + 半同步（source_status=ON, clients=1）
- **RAG**：LangChain + Chroma 知识库骨架（ingest/retrieve/evaluate），待实测参数对比表

## 博客文章（掘金，已发布 4 篇）

| 文章 | 链接 | 对应实验 |
|---|---|---|
| 一次慢查询优化：从 512ms 到 0.0135ms，我把一条 SQL 提速了 3.8 万倍 | https://juejin.cn/post/7712130561377435684 | 笔记 06 / 实验 6 |
| 误删表之后：mysqldump + binlog 时间点恢复实战（附完整排错） | https://juejin.cn/post/7712274520749375529 | 笔记 03 / 实验 3 |
| MySQL 8 用户权限管理：从授权到越权验证 | https://juejin.cn/post/7712274520749408297 | 笔记 02 / 实验 2 |
| CentOS 7 装 MySQL 8.0：EOL 之后的完整踩坑记录 | https://juejin.cn/post/7712359514977353769 | 笔记 01 / 实验 1 |
