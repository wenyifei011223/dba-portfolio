# 07 锁等待与死锁排查

## 1. 实验环境

- 承袭前序：MySQL 8.0.43 + `sbtest.sbtest1`（100 万行）
- 开 3 个独立会话窗口，全部连主库 node1（从库有 `super_read_only` 不能写）
- 截图：S53–S57（均已上传 `mysql-ops/07-lock-deadlock/`）

## 2. 问题现象（踩坑记录，博客素材）

**坑 1：SQL 敲在 shell 提示符下** — 窗口提示符是 `[root@node1 ~]#` 时，`BEGIN;`、`UPDATE...` 会被当成 Linux 命令，报"未找到命令"。必须先 `mysql -uroot -p...` 进入，看到 `mysql>` 提示符再敲 SQL。

**坑 2：进了 mysql 又敲登录命令** — 已经在 `mysql>` 里还敲 `mysql -uroot -p...`，它和下一行 SQL 拼成一条，报 `ERROR 1064`。**判断方法**：`mysql>` 后只能贴 SQL，`#` 后才能贴 shell 命令。

**坑 3：SQL 少了分号不执行** — mysql 命令行里语句必须以 `;`（或 `\G`）结尾，否则只出现 `->` 等你继续输入，不会执行。

**坑 4：锁等待超时，抓不到卡住现场** — MySQL 默认 `innodb_lock_wait_timeout=50` 秒，B 等太久会报 `ERROR 1205 Lock wait timeout exceeded`，卡住的画面就没了。所以 A 锁住后，B 一卡住要**立刻截图**，再切 C 排查。

**坑 5：`\G` 后面加分号报错** — `SELECT ... \G` 本身就是结束符，再加 `;` 会报错。正确写法：`SELECT * FROM information_schema.innodb_trx\G` 直接回车。

**坑 6：`data_lock_waits` 查出来是 Empty set** — 因为排查太慢，B 已经超时不在等待状态了。三个排查工具要在 50 秒窗口内连贯执行。

## 3. 操作过程

**第一部分：锁等待**

**① 会话 A —— 开事务改 id=1 不提交**（制造阻塞源）

```sql
BEGIN;
UPDATE sbtest.sbtest1 SET k=k+1 WHERE id=1;
```

**② 会话 B —— 改同一行，卡住**

```sql
UPDATE sbtest.sbtest1 SET k=k+1 WHERE id=1;
```

回车后光标停住、无输出 = 正在等锁。立刻截图。

![S53 会话 B 卡住等待](<../mysql-ops/07-lock-deadlock/S53-lock-wait.jpg>)

**③ 会话 C —— 排查阻塞源**（三个工具）

```sql
SELECT * FROM information_schema.innodb_trx\G
```

看到 `trx_id: 77984`、`trx_state: RUNNING`、`trx_mysql_thread_id: 64`、`trx_rows_locked: 1`、`trx_rows_modified: 1`——这就是 A 那个未提交事务在持锁。

![S54 innodb_trx 未提交事务](<../mysql-ops/07-lock-deadlock/S54-innodb-trx.jpg>)

```sql
SELECT * FROM performance_schema.data_lock_waits;    -- 谁等谁
SHOW ENGINE INNODB STATUS\G                          -- TRANSACTIONS 段
```

`SHOW ENGINE INNODB STATUS` 的 `TRANSACTIONS` 段能看到 `---TRANSACTION 77984, ACTIVE 250 sec`、`1 row lock(s)`、`undo log entries 1`。

![S55 INNODB STATUS TRANSACTIONS 段](<../mysql-ops/07-lock-deadlock/S55-innodb-status.jpg>)

**④ 杀掉阻塞源**

```sql
KILL 64;                -- 用上面查到的 trx_mysql_thread_id
```

执行后 B 的 UPDATE 立刻返回 `Query OK`，锁解开。

**第二部分：死锁复现**

两个会话以相反顺序更新两行，制造环形等待：

```sql
-- 会话 A：BEGIN; UPDATE ... WHERE id=1;  然后  UPDATE ... WHERE id=2;
-- 会话 B：BEGIN; UPDATE ... WHERE id=2;  然后  UPDATE ... WHERE id=1;
```

A 拿 id=1 等 id=2，B 拿 id=2 等 id=1——形成环，InnoDB 立刻检测到死锁，回滚代价小的事务，另一个报：

```
ERROR 1213 (40001): Deadlock found when trying to get lock; try restarting transaction
```

![S56 ERROR 1213 死锁报错](<../mysql-ops/07-lock-deadlock/S56-deadlock-error.jpg>)

在 `SHOW ENGINE INNODB STATUS\G` 的 `LATEST DETECTED DEADLOCK` 段能看到完整日志：两个事务各自 `HOLDS THE LOCK(S)` 和 `WAITING FOR THIS LOCK TO BE GRANTED`，以及最后 `WE ROLL BACK TRANSACTION (n)`。

![S57 LATEST DETECTED DEADLOCK 日志](<../mysql-ops/07-lock-deadlock/S57-deadlock-log.jpg>)

## 4. 关键概念说明（面试重点）

**① 三个排查工具各看什么**

| 工具 | 看什么 |
|---|---|
| `information_schema.innodb_trx` | 当前所有 InnoDB 事务，重点看 `trx_state`、`trx_mysql_thread_id`（KILL 用）、`trx_rows_locked` |
| `performance_schema.data_lock_waits` | 锁等待关系：谁（REQUESTING）在等谁（BLOCKING） |
| `SHOW ENGINE INNODB STATUS\G` | 完整锁信息，`TRANSACTIONS` 段看事务和锁，`LATEST DETECTED DEADLOCK` 段看最近死锁 |

**② 锁等待 vs 死锁**

- 锁等待：一个事务持锁不放，另一个等着，等超过 `innodb_lock_wait_timeout`（默认 50s）报 ERROR 1205。**不会自动解开**，要 KILL 阻塞源或等它提交/回滚。
- 死锁：两个及以上事务互相持有对方要的锁，形成环。InnoDB **自动检测**（等待图检测），选回滚代价最小的事务打破环，另一个报 ERROR 1213。应用应该捕获 1213 并重试。

**③ 减少死锁的实践**

固定更新顺序（都按 id 升序）、缩短事务、避免大事务、加合适索引让锁粒度更小（行锁而非表锁）。

## 5. 复盘 / 面试怎么讲

> 锁等待我用三个会话复现：A 开事务更新 id=1 不提交持有排他锁，B 更新同一行卡住，C 用 `innodb_trx` 找到未提交事务的 `trx_mysql_thread_id`，用 `data_lock_waits` 看等待关系，再用 `SHOW ENGINE INNODB STATUS` 的 TRANSACTIONS 段确认，最后 KILL 掉阻塞源，B 立刻执行成功。
>
> 死锁是两个会话以相反顺序更新两行触发环形等待，InnoDB 自动检测到并回滚代价小的事务，另一个报 ERROR 1213，在 `LATEST DETECTED DEADLOCK` 段能看到两个事务互相持锁的完整日志。
>
> 排错踩了几个坑：SQL 敲在 shell 提示符下、进了 mysql 又敲登录命令报 1064、SQL 少分号不执行、`\G` 加分号报错、排查太慢导致 B 超时抓不到现场、`data_lock_waits` 查出来是空的——都是靠看提示符、控制操作节奏、用对结束符解决的。这让我对"看提示符判断当前环境"和"锁等待 50 秒窗口"印象特别深。
