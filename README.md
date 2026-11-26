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
- `notes/` 故障复盘笔记（持续更新）
- `rag-knowledge-base/` RAG 私有知识库（进行中）

## 环境
VMware Workstation + CentOS 7 + MySQL 8.0；Percona XtraBackup 8.0；Python 3.10 + LangChain

## 亮点结果
- **慢查询优化**：EXPLAIN `type` 由 `ALL` → `range`，扫描行数 986400 → 1，实际耗时 **512ms → 0.0135ms**（sysbench 400 万行数据集）
- **压测基线**：8 线程 60 秒，TPS 467 / QPS 9345 / 95% 延迟 30.26ms
- **备份恢复**：mysqldump + binlog PITR、XtraBackup 全量 + 增量恢复均已验证
- **主从复制**：GTID 自动定位 + 延迟演练 + 半同步（source_status=ON, clients=1）
- **RAG**：文档入库与参数对比（进行中）

## 博客文章
- 待发布后回填
