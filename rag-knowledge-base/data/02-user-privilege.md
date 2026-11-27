# 02 MySQL 8.0 用户与权限管理

## 1. 实验环境

- 承袭笔记 01：VMware Workstation 17.5.2 + CentOS 7.9（最小安装，8GB 内存 / 50GB 磁盘，NAT，IP 192.168.88.128）
- MySQL 8.0.43，系统 root 与 MySQL root 密码均为 `root`（仅本地实验）
- 测试库 `testdb`，表 `t1(id INT PRIMARY KEY, name VARCHAR(20))`，测试数据 `(1,'a')`、`(2,'b')`
- 两个会话并行：root 管理员会话（授权/回收）+ app 普通用户会话（越权验证）
- 截图：S15–S22（均已上传 `mysql-ops/02-user-privilege/`）

## 2. 问题现象（踩坑记录，博客素材）

这次实验的"坑"分两类：一类是 MySQL 权限机制本身的知识点，一类是操作失误。后者看起来低级，但正是真实排错过程的体现，面试讲出来反而加分。

**坑 1：MySQL 8 不能像 5.7 那样"GRANT 时顺带建用户"** — 直接 `GRANT ... TO 'app'@'%'` 会报 `ERROR 1064`。MySQL 8 把"创建用户"和"授权"拆成两条语句，必须先 `CREATE USER` 再 `GRANT`。这是版本差异，也是高频面试点（详见第 4 节）。

**坑 2：越权报错 ERROR 1142 是"预期结果"** — `DELETE`/`INSERT` 被拒时输出 `ERROR 1142 (42000): ... command denied`。这不是故障，恰恰是**最小权限生效的铁证**。用一张报错原文图证明，比任何文字都有说服力（这是博客 2 的核心素材）。

**坑 3：把 shell 命令贴进了 `mysql>` 会话** — `sed`、`systemctl`、`cat` 这类命令贴到 `mysql>` 后面，会被当成没写完的 SQL，屏幕出现满屏 `->` 续行符，一条都没执行。**判断方法**：提示符是 `mysql>` 只能贴 SQL，`[root@node1 ~]#` 才能贴 shell 命令；看到 `->` 就按 `Ctrl+C` 退出重贴。

**坑 4：sed 正则被转义工具破坏** — 想用 `sed -i '/\[mysqld\]/a skip-grant-tables'` 追加配置，结果命令里的 `\[mysqld\]` 被某个粘贴工具转义成了 `$$mysqld$$`，正则匹配不到，`grep` 无输出、配置根本没写进去。`-e` 方式里也有类似问题。**解法**：放弃 sed，改用不带正则的整段覆盖 `cat > /etc/my.cnf << 'EOF'`，一次写死最稳。

**坑 5：改弱密码报 ERROR 1819 / `-e` 方式降策略不生效** — 把 root 密码设成 `root`（4 位）会被默认策略拒绝。必须先把 `validate_password.policy` 降到 LOW、长度允许 4 位、关闭用户名检查。**关键**：`SET GLOBAL` 要在交互式 `mysql>` 里执行才生效，塞进 `mysql -e "..."` 里不生效（照样报 1819），最终用交互式一次贴完才成功。

## 3. 操作过程

**第 1 步：建库建表 + 建用户授权**（root 会话）

```sql
CREATE DATABASE testdb;
CREATE TABLE testdb.t1(id INT PRIMARY KEY, name VARCHAR(20));
INSERT INTO testdb.t1 VALUES(1,'a'),(2,'b');
DROP USER IF EXISTS 'app'@'%';           -- 清理 Day 1 建的旧用户（当时范围是整个库）
CREATE USER 'app'@'%' IDENTIFIED BY 'App@123456';
GRANT SELECT,INSERT ON testdb.* TO 'app'@'%';
SHOW GRANTS FOR 'app'@'%';
```

`SHOW GRANTS` 输出两行：

```
GRANT USAGE ON *.* TO 'app'@'%'
GRANT SELECT, INSERT ON `testdb`.* TO 'app'@'%'
```

> 第一条 DROP 把 Day 1 那个 `*.*` 全库权限的 app 收敛到 `testdb.*`，体现"最小权限"思路本身就是一个面试点。

![S15 授权结果](<../mysql-ops/02-user-privilege/S15-建库、建用户、授权.jpg>)

**第 2 步：越权验证**（另开会话，app 登录）

```sql
SELECT * FROM testdb.t1;                 -- 成功：返回 1 a / 2 b
DELETE FROM testdb.t1 WHERE id=1;        -- 被拒：ERROR 1142 DELETE command denied
```

![S16 查询成功](<../mysql-ops/02-user-privilege/S16-查询表.jpg>)

![S17 DELETE 被拒 ERROR 1142](<../mysql-ops/02-user-privilege/S17-删除表.jpg>)

![S17-1 越权验证](<../mysql-ops/02-user-privilege/S17-1越权验证.jpg>)

**第 3 步：回收权限并验证**（回 root 会话）

```sql
REVOKE INSERT ON testdb.* FROM 'app'@'%';
FLUSH PRIVILEGES;
SHOW GRANTS FOR 'app'@'%';               -- 只剩 SELECT，INSERT 没了
```

切到 app 会话执行：

```sql
INSERT INTO testdb.t1 VALUES(3,'c');     -- 被拒：ERROR 1142 INSERT command denied
```

> 权限变更对已连接的会话**立即生效**，app 不用重登，直接 INSERT 就被拒。

![S18 回收后授权](<../mysql-ops/02-user-privilege/S18-回收权限.jpg>)

![S19 INSERT 被拒](<../mysql-ops/02-user-privilege/S19-回收权限后验证.jpg>)

## 4. 关键概念说明（面试重点）

**① MySQL 8 创建用户与授权必须分两条语句**

MySQL 5.7 里 `GRANT ... TO user` 会自动创建用户；MySQL 8 移除了这个行为，必须：

```sql
CREATE USER 'app'@'%' IDENTIFIED BY 'App@123456';
GRANT SELECT ON testdb.* TO 'app'@'%';
```

**② 认证插件 `caching_sha2_password`**

MySQL 8 默认认证插件是 `caching_sha2_password`（比 5.7 的 `mysql_native_password` 更快更安全），但一些老客户端（旧版 Navicat、JDBC 驱动）不支持，会报认证失败。兼容老客户端可改：

```sql
ALTER USER 'app'@'%' IDENTIFIED WITH mysql_native_password BY 'App@123456';
```

**③ 权限矩阵与 `USAGE` 的含义**

| 阶段 | SELECT | INSERT | DELETE |
|---|:---:|:---:|:---:|
| 授权后（S15） | ✅ | ✅ | ❌ |
| 回收 INSERT 后（S18） | ✅ | ❌ | ❌ |

`GRANT USAGE ON *.*` 是新建用户自带的"空权限"——表示账号能连上但什么也做不了，真正权限由下面那行决定。

**④ 最小权限原则（Least Privilege）**

只给账号完成工作所必需的最小权限。app 只需要读，就别给 INSERT/DELETE；能把权限收敛到库级 `testdb.*`，就别给全库 `*.*`。**用报错图（S17/S19）证明"没给的权限真的用不了"**，是最有说服力的证据。

## 5. 忘记 root 密码演练（高频故障，博客第 2 个素材点）

原理：在 `[mysqld]` 下临时加 `skip-grant-tables` 让 MySQL 跳过权限验证 → 无密码进入 → 改密码 → 删掉配置恢复。

**第①段：加配置、重启** 【截图 S20】

```bash
echo skip-grant-tables >> /etc/my.cnf
cat /etc/my.cnf          # 确认能看到 skip-grant-tables
systemctl restart mysqld
```

![S20 免密配置行](<../mysql-ops/02-user-privilege/S20-加配置.jpg>)

**第②段：无密码进入 + 降策略改密码** 【截图 S21】

```bash
mysql -u root            # 不用 -p，直接进
```

看到 `mysql>` 后，整段贴（含 `exit`，执行完自动退回 shell）：

```sql
FLUSH PRIVILEGES;
SET GLOBAL validate_password.policy = LOW;
SET GLOBAL validate_password.length = 4;
SET GLOBAL validate_password.check_user_name = OFF;
ALTER USER 'root'@'localhost' IDENTIFIED BY 'root';
FLUSH PRIVILEGES;
exit
```

> 第一条 `FLUSH PRIVILEGES` 不能省：`skip-grant-tables` 模式下权限系统未加载，不先 FLUSH 直接 ALTER USER 会报 `ERROR 1290`。

![S21 改密成功](<../mysql-ops/02-user-privilege/S21-进 MySQL + 改密码.jpg>)

**第③段：删配置 + 重启 + 验证** 【截图 S22】

```bash
cat > /etc/my.cnf << 'EOF'
[mysqld]
bind-address=0.0.0.0
datadir=/var/lib/mysql
socket=/var/lib/mysql/mysql.sock
port=3306
character-set-server=utf8mb4
collation-server=utf8mb4_0900_ai_ci
default-time-zone='+8:00'
max_connections=200
innodb_buffer_pool_size=512M
log-error=/var/log/mysqld.log
EOF
grep skip-grant /etc/my.cnf            # 必须无输出：配置已删干净
systemctl restart mysqld
mysql -uroot -proot -e "SELECT 1;"     # 输出 1：新密码生效
```

![S22 恢复后登录](<../mysql-ops/02-user-privilege/S22-恢复配置.jpg>)

**安全红线**：`skip-grant-tables` 让 MySQL 处于无密码状态，实验完**必须确认已删除**（第③步 `grep` 无输出）。面试被问"怎么保证数据库安全"时，这是加分回答点。

## 6. 复盘 / 面试怎么讲

> 我在 MySQL 8 上做了完整的用户权限实验：创建 app 用户并授权 `testdb.*` 的 SELECT/INSERT，用 `SHOW GRANTS` 确认授权结果；再用 app 会话做越权验证——有权限的 SELECT 成功，没给的 DELETE 报 ERROR 1142，回收 INSERT 后再 INSERT 也被拒，用报错原文图证明最小权限真正生效。
>
> 面试点我特意验证了三个：一是 MySQL 8 创建用户和授权必须分两条语句，5.7 可以合并；二是默认认证插件是 `caching_sha2_password`，老客户端兼容要改 `mysql_native_password`；三是 `USAGE` 只表示能登录、无实际权限。
>
> 还做了一遍忘记 root 密码的演练：临时加 `skip-grant-tables` 无密码进入，先 `FLUSH PRIVILEGES` 再降密码策略改密，最后删掉配置重启恢复。安全上最重要的是确认 `skip-grant-tables` 已删除，否则数据库无密码运行。排错过程中踩了几个坑——shell 命令贴进 `mysql>` 变成 `->` 续行、sed 正则被粘贴工具转义破坏、`SET GLOBAL` 在 `-e` 方式里不生效——都是靠看提示符、换整段覆盖、改交互式逐条解决的。
