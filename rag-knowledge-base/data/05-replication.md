# 05 MySQL 8.0 主从复制（GTID + 延迟 + 半同步）

## 1. 实验环境

- 承袭笔记 01：VMware Workstation 17.5.2 + CentOS 7.9，MySQL 8.0.43
- 两台虚拟机：主库 node1（192.168.88.128）、从库 node2（克隆机，需删 `auto.cnf` 避免 UUID 冲突）
- 复制用户 `repl`@`%`，密码 `Repl@123`，授予 `REPLICATION SLAVE`
- GTID 模式：`gtid_mode=ON` + `enforce_gtid_consistency=ON`
- 截图：S24、S37–S44（均已上传 `mysql-ops/05-replication/`）

## 2. 问题现象（踩坑记录，博客素材）

**坑 1：克隆机没删 `auto.cnf`，从库 IO 线程起不来** — 两台机器的 `server_uuid` 相同，报 `Fatal error: The slave I/O thread stops because master and slave have equal MySQL server UUIDs`。解法：`rm -f /var/lib/mysql/auto.cnf` 后重启 mysqld，让它重新生成。

**坑 2：IO 线程一直 `Connecting`，认证失败** — 主库 `Last_IO_Error` 报 `Authentication plugin 'caching_sha2_password' cannot be loaded`。MySQL 8 默认认证插件在复制连接时客户端拿不到公钥，解法：`CHANGE REPLICATION SOURCE TO ... GET_SOURCE_PUBLIC_KEY=1`，让主库把公钥发给从库。

**坑 3：翻倍命令在从库执行，报 ERROR 1290** — 从库设了 `super_read_only=ON` 后，连 root 都不能写。造延迟数据的翻倍 `INSERT` 必须在**主库 node1** 执行（看提示符 `[root@node1 ~]#`），在 node2 执行会报 `ERROR 1290 (HY000) ... --super-read-only option`，一行都写不进去。

**坑 4：延迟 `Seconds_Behind_Source` 抓不到非零值** — 数据量小、回放太快，还没截到就追平了（显示 0 或 NULL）。解法：造一批**大 UPDATE**（几十万行），`STOP REPLICA` → 主库灌数据 → `START REPLICA` 后**立刻**查，才能抓到增长中的数字。

**坑 5：SQL 线程报 ERROR 1032（row not found）** — 从库回放时找不到对应行，复制中断。解法：GTID 跳过法——取出错事务的 GTID，`STOP REPLICA; SET GTID_NEXT='uuid:N'; BEGIN; COMMIT; SET GTID_NEXT='AUTOMATIC'; START REPLICA;`，注入一个空事务跳过。前提是确认跳过的是可容忍的数据差异（实验环境可接受）。

**坑 6：半同步插件装不上（两个连环错）** — 先报 `ERROR 1290 ... --super-read-only`（因为 S41 设过 `super_read_only=ON`，拦住了 `INSTALL PLUGIN`），紧接着设变量报 `ERROR 1193 ... Unknown system variable`（因为插件根本没装上）。解法：`SET GLOBAL super_read_only=OFF;` → 装插件 → 设 enabled=1 → 再设回 ON → `STOP/START REPLICA` 让协商生效。

**坑 7：半同步从库状态显示 OFF** — `SET GLOBAL rpl_semi_sync_replica_enabled=1` 之后必须重启复制线程才会翻成 ON，光设变量不够。

## 3. 操作过程

**第 1 步：主库准备 + 建复制用户**

```sql
-- 主库 node1
CREATE USER 'repl'@'%' IDENTIFIED BY 'Repl@123';
GRANT REPLICATION SLAVE ON *.* TO 'repl'@'%';
SHOW MASTER STATUS;                    -- 记下 File 和 Position
```

![S37 主库状态](<../mysql-ops/05-replication/S37-master-status.jpg>)

**第 2 步：从库配置复制（GTID 自动定位）**

两台机器的 `/etc/my.cnf` 都加 `gtid_mode=ON`、`enforce_gtid_consistency=ON`，从库再加 `relay-log`、`read_only`、`super_read_only`。改完 `systemctl restart mysqld`。

克隆机先删 UUID：

```bash
rm -f /var/lib/mysql/auto.cnf
```

从库执行（8.0.23+ 用新语法 SOURCE/REPLICA）：

```sql
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST='192.168.88.128',
  SOURCE_USER='repl',
  SOURCE_PASSWORD='Repl@123',
  SOURCE_AUTO_POSITION=1,
  GET_SOURCE_PUBLIC_KEY=1;
START REPLICA;
SHOW REPLICA STATUS\G
```

**验收标准**：`Replica_IO_Running: Yes` + `Replica_SQL_Running: Yes`（双 Yes）、`Last_SQL_Error` 空、`Retrieved_Gtid_Set` = `Executed_Gtid_Set`。

![S38 双 Yes](<../mysql-ops/05-replication/S38-replica-status-yes.jpg>)

**第 3 步：主从同步验证**

主库插数据，从库查到：

```sql
-- 主库
INSERT INTO testdb.t1 VALUES(6,'f');
-- 从库
SELECT * FROM testdb.t1;               -- 能看到 6 f
```

![S39 主库插入](<../mysql-ops/05-replication/S39-master-insert.jpg>)

![S40 从库同步](<../mysql-ops/05-replication/S40-replica-synced.jpg>)

**第 4 步：从库只读验证**

```sql
-- 从库 node2，root 用户
INSERT INTO testdb.t1 VALUES(7,'g');   -- ERROR 1290，super_read_only 生效
```

![S41 从库只读](<../mysql-ops/05-replication/S41-replica-readonly.jpg>)

**第 5 步：延迟演练**

```sql
-- 从库：停 SQL 线程
STOP REPLICA SQL_THREAD;
-- 主库：大批量写入（必须在主库！）
INSERT INTO testdb.t1 SELECT ... ;     -- 反复翻倍造几十万行
-- 从库：立刻查延迟
SHOW REPLICA STATUS\G                  -- Seconds_Behind_Source: 增长中
-- 从库：恢复
START REPLICA SQL_THREAD;
SHOW REPLICA STATUS\G                  -- Seconds_Behind_Source: 0
```

![S42 延迟增长](<../mysql-ops/05-replication/S42-delay-growing.jpg>)

![S43 延迟追平](<../mysql-ops/05-replication/S43-delay-zero.jpg>)

> 追平后确认 `Retrieved_Gtid_Set` = `Executed_Gtid_Set`、`Last_SQL_Error` 空。中途遇到 1032 用 GTID 空事务跳过（见坑 5）。

**第 6 步：半同步复制（加分）**

```sql
-- 主库
INSTALL PLUGIN rpl_semi_sync_source SONAME 'semisync_source.so';
SET GLOBAL rpl_semi_sync_source_enabled=1;
SHOW STATUS LIKE 'Rpl_semi_sync_source_status';    -- ON
SHOW STATUS LIKE 'Rpl_semi_sync_source_clients';   -- 1

-- 从库（先解 super_read_only）
SET GLOBAL super_read_only=OFF;
INSTALL PLUGIN rpl_semi_sync_replica SONAME 'semisync_replica.so';
SET GLOBAL rpl_semi_sync_replica_enabled=1;
SHOW STATUS LIKE 'Rpl_semi_sync_replica_status';   -- ON
SET GLOBAL super_read_only=ON;
STOP REPLICA; START REPLICA;
```

![S44 半同步三合一（主库 status=ON + clients=1 + 从库 status=ON）](<../mysql-ops/05-replication/S44-semisync-on.jpg>)

> 版本坑：8.0.26+ 用 `source`/`replica` 命名和 `semisync_source.so`/`semisync_replica.so`；老教程的 `master`/`slave` 和 `semisync_master.so` 在新版会报错。

## 4. 关键概念说明（面试重点）

**① 复制三线程**

主库 dump 线程读 binlog 发给从库 → 从库 IO 线程接收写 relay log → 从库 SQL 线程回放 relay log。异步复制主库不等待从库确认；半同步至少等一个从库收到 relay log 才返回。

**② GTID 自动定位**

`SOURCE_AUTO_POSITION=1` 后不用手工对 binlog 文件名和位点，从库用 `Executed_Gtid_Set` 告诉主库"我执行到哪了"，主库自动补发缺失事务。切换/故障恢复比位点法可靠得多。

**③ `Seconds_Behind_Source` 的含义**

从库 SQL 线程落后主库的秒数。为 0 表示追平，NULL 表示 SQL 线程停了（延迟演练时 STOP 期间就是 NULL）。它衡量的是回放延迟，不是网络延迟。

**④ 新旧命令对照（8.0.23 分水岭）**

| 旧语法（≤8.0.22） | 新语法（≥8.0.23） |
|---|---|
| `CHANGE MASTER TO` | `CHANGE REPLICATION SOURCE TO` |
| `MASTER_HOST` / `MASTER_LOG_FILE` | `SOURCE_HOST` / `SOURCE_LOG_FILE` |
| `START SLAVE` | `START REPLICA` |
| `SHOW SLAVE STATUS` | `SHOW REPLICA STATUS` |
| `Seconds_Behind_Master` | `Seconds_Behind_Source` |

> 8.4 已完全移除旧语法，必须写新的。

## 5. 复盘 / 面试怎么讲

> 我用两台 CentOS 虚拟机做了完整的 MySQL 8 主从复制：主库建 `repl` 复制用户，从库用 `CHANGE REPLICATION SOURCE TO ... SOURCE_AUTO_POSITION=1` 配 GTID 自动定位，验收双 Yes 且 GTID 集合一致，主库插数据从库能查到。
>
> 延迟我复现了：停从库 SQL 线程、在主库造几十万行，用 `Seconds_Behind_Source` 观察增长，恢复后追平回 0。中途遇到 SQL 线程 1032 报错，用 GTID 注入空事务跳过。
>
> 排错过程踩了几个典型坑：克隆机 UUID 冲突、caching_sha2 认证公钥问题（加 `GET_SOURCE_PUBLIC_KEY=1`）、翻倍命令误在从库执行触发 1290、半同步插件被 super_read_only 拦住导致连环报错。这些我都能讲清现象、原因和解法。
>
> 最后配了半同步复制，主库 `Rpl_semi_sync_source_status=ON`、`clients=1`，从库 `replica_status=ON` 三张图合成一张作为证据——只截主库 status=ON 不够，`clients=1` 才能证明真有从库连着。
