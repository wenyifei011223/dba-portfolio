# dba-portfolio
MySQL 运维实操 + 故障案例复盘 + RAG 知识库实践

# DBA 学习与实战实验仓库

> MySQL 运维实操 + 故障案例复盘 + RAG 知识库实践
> 所有实验均在本人虚拟机环境真实执行，附完整命令、截图与结果。

## 目录
- `mysql-ops/00-environment/` 环境与安装
- `mysql-ops/02-user-privilege/` 用户与权限
- `notes/` 8 篇故障复盘笔记
- `rag-knowledge-base/` RAG 私有知识库（进行中）

## 环境
VMware Workstation + CentOS 7 + MySQL 8.0；Percona XtraBackup 8.0；Python 3.10 + LangChain

## 亮点结果
- 慢查询优化：EXPLAIN ANALYZE 实际耗时 待测 → 待测
- 备份恢复：mysqldump + binlog PITR、XtraBackup 全量 + 增量（进行中）
- 主从复制：异步 / 半同步 + GTID（进行中）
- RAG：文档入库与参数对比（进行中）

## 博客文章
- 待发布后回填
