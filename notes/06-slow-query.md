# 06 慢查询定位与优化（sysbench + EXPLAIN）

## 1. 实验环境

- 承袭前序：VMware Workstation + CentOS 7.9 + MySQL 8.0.43
- sysbench 1.0.20，`oltp_read_write` 造 4 张表、每张 100 万行（共 400 万行）的 `sbtest` 库
- 压测参数：8 线程、60 秒、`--report-interval=10`
- 截图：S45–S51（均已上传 `mysql-ops/06-slow-query/`）

## 2. 问题现象（踩坑记录，博客素材）

**坑 1：yum 装不上 sysbench** — CentOS 7 已 EOL，官方源失效；换成阿里云 vault 源后 `base/updates/extras` 里仍可能没有 sysbench，报 `No package sysbench available`。先 `yum list sysbench` 确认，实测配了 Percona 源的机器能装上 1.0.20。

**坑 2：sysbench 连不上 MySQL，报 2059 认证错** — `FATAL: error 2059: Authentication plugin 'caching_sha2_password' cannot be loaded`。sysbench 1.0.20 自带的客户端库不支持 MySQL 8 默认认证插件。解法：把 root 改成老版认证（密码不变，不影响复制用户）：

```sql
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'NewPass@123';
```

**坑 3：prepare 特别慢** — 主库开着半同步，每个事务要等从库确认，400 万行灌入比平时慢很多。属正常，别 Ctrl+C。

**坑 4：耗时数字忽高忽低** — 冷缓存第一次偏慢。前后各跑 2–3 次取稳定值，用同样方法测才公平，不能只抄一个自己解释不了的数字。

## 3. 操作过程

**第 1 步：造数据**

```bash
yum install -y sysbench
mysql -uroot -pNewPass@123 -e "CREATE DATABASE IF NOT EXISTS sbtest;"
sysbench oltp_read_write --db-driver=mysql --mysql-host=127.0.0.1 \
  --mysql-user=root --mysql-password='NewPass@123' --mysql-db=sbtest \
  --tables=4 --table-size=1000000 prepare
```

![S45 造数据完成](<../mysql-ops/06-slow-query/S45-sysbench-prepare.jpg>)

**第 2 步：压测拿 TPS/QPS**

```bash
sysbench oltp_read_write --db-driver=mysql --mysql-host=127.0.0.1 \
  --mysql-user=root --mysql-password='NewPass@123' --mysql-db=sbtest \
  --tables=4 --table-size=1000000 --threads=8 --time=60 --report-interval=10 run
```

实测结果：**TPS 467/s、QPS 9345/s、95% 延迟 30.26ms**（8 线程 60 秒，28 万事务，0 错误）。

![S46 压测报告](<../mysql-ops/06-slow-query/S46-sysbench-run.jpg>)

**第 3 步：复现慢查询（确认全表扫描）**

```sql
EXPLAIN SELECT * FROM sbtest.sbtest1 WHERE LEFT(pad,10)='abcdefghij';
```

结果：`type=ALL`、`key=NULL`、`rows=986400`、`Extra=Using where`——**函数 `LEFT()` 包裹列导致索引失效，走全表扫描**。

![S47 优化前 EXPLAIN：type=ALL, rows=986400](<../mysql-ops/06-slow-query/S47-explain-before.jpg>)

```sql
EXPLAIN ANALYZE SELECT * FROM sbtest.sbtest1 WHERE LEFT(pad,10)='abcdefghij';
```

实际耗时 **512ms**（`Table scan ... rows=1e6`）。

![S48 优化前实际耗时 512ms](<../mysql-ops/06-slow-query/S48-explain-analyze-before.jpg>)

**第 4 步：优化 + 验证**

路线：对 `pad` 建前缀索引，把函数运算改写成前缀匹配（同一个查询需求，对比最有说服力）：

```sql
ALTER TABLE sbtest.sbtest1 ADD INDEX idx_pad(pad(20));
EXPLAIN SELECT * FROM sbtest.sbtest1 WHERE pad LIKE 'abcdefghij%';
EXPLAIN ANALYZE SELECT * FROM sbtest.sbtest1 WHERE pad LIKE 'abcdefghij%';
```

优化后：`type=range`、`key=idx_pad`、`key_len=80`、`rows=1`——索引生效，只扫 1 行。实际耗时 **0.0135ms**。

![S49 优化后 EXPLAIN：type=range, key=idx_pad, rows=1](<../mysql-ops/06-slow-query/S49-explain-after.jpg>)

![S50 优化后实际耗时 0.0135ms](<../mysql-ops/06-slow-query/S50-explain-analyze-after.jpg>)

**前后对比拼图**（简历佐证 / 博客封面）：

![S51 优化前后 EXPLAIN 对比](<../mysql-ops/06-slow-query/S51-explain-compare.jpg>)

**第 5 步：效果汇总**

| 指标 | 优化前 | 优化后 |
|---|---|---|
| type | ALL（全表扫描） | range（索引范围） |
| key | NULL | idx_pad |
| rows | 986400 | 1 |
| EXPLAIN ANALYZE 耗时 | 512ms | 0.0135ms |

> 压测基线：TPS 467 / QPS 9345 / 95% 延迟 30.26ms。

## 4. 关键概念说明（面试重点）

**① 为什么对列做函数运算索引会失效**

索引里存的是列的原始值（B+ 树按 `pad` 原值排序）。`LEFT(pad,10)` 是对每行算出一个新值再比较，优化器无法用 `pad` 的原始 B+ 树定位，只能全表扫描逐行算。口诀：**让索引列"裸奔"**——别用函数、别做隐式转换、别用 `%` 开头的 LIKE。

**② EXPLAIN 关键列怎么读**

- `type`：访问类型，`ALL`（全表）< `index` < `range` < `ref` < `eq_ref` < `const`。优化目标是把 ALL 降到 ref/range。
- `key`：实际用到的索引，`NULL` 表示没用索引。
- `rows`：预估扫描行数，越小越好。
- `Extra`：`Using where` 表示过滤；出现 `Using filesort`/`Using temporary` 要警惕。

**③ 前缀索引**

`ADD INDEX idx_pad(pad(20))` 只对前 20 个字符建索引，适合长字符串列，省空间。配合 `LIKE 'abcdefghij%'`（前缀匹配、 `%` 在末尾）才能用上；`LIKE '%abc'` 用不上。

**④ 覆盖索引**

如果查询的所有列都在索引里，不用回表查主键记录，更快。这是进一步的优化方向。

## 5. 复盘 / 面试怎么讲

> 我用 sysbench 造了 400 万行数据，先跑 8 线程 60 秒压测拿到基线（TPS 467、QPS 9345、95% 延迟 30.26ms）。然后复现一条慢查询：用 `LEFT(pad,10)` 函数包裹列，EXPLAIN 显示 `type=ALL`、`rows` 近 100 万，EXPLAIN ANALYZE 实测 512ms——根因是对列做函数运算让索引失效。
>
> 优化方式是对 `pad` 建前缀索引、把函数改写成 `LIKE 'abcdefghij%'` 前缀匹配。优化后 `type` 从 ALL 变 range，`rows` 从 98 万降到 1，实际耗时从 512ms 降到 0.0135ms。前后两张 EXPLAIN 拼成一张图，一眼就能看出变化。
>
> 排错踩了几个坑：CentOS 7 EOL 后 yum 源问题、sysbench 1.0.20 不支持 caching_sha2 认证（2059 报错，改 native 认证解决）、半同步下 prepare 变慢、耗时数字取稳定值要多次跑。每个坑都能讲清现象和解法。
