# 04 XtraBackup 全量 + 增量备份恢复

## 1. 实验环境

- 承袭笔记 01：VMware Workstation + CentOS 7.9，MySQL 8.0.43
- 备份工具：Percona XtraBackup 8.0.35-31（物理备份，基于 MySQL 8.0.35）
- 备份目录：`/backup/full`（全量）、`/backup/inc1`（增量）
- 截图：S30–S36（均已上传 `mysql-ops/04-xtrabackup/`）

## 2. 问题现象（踩坑记录，博客素材）

**坑 1：Percona 源 `yum install percona-release` 卡死** — 国内访问 Percona 超时，`%post` 联网脚本卡在 `Running transaction`。`Ctrl+C` 中断后显示 `Non-fatal POSTIN scriptlet failure`，**这是非致命的**，RPM 包本身已装（`rpm -qa percona-release` 可证实）。此时别再跑 `percona-release enable-only`（同样卡死），直接手写 repo 文件（xtrabackup 在 tools 仓库）：

```bash
cat > /etc/yum.repos.d/percona-tools.repo <<'EOF'
[percona-tools]
name=Percona Tools
baseurl=https://mirrors.tuna.tsinghua.edu.cn/percona/tools/yum/release/7/RPMS/x86_64/
enabled=1
gpgcheck=0
EOF
yum clean all
yum install -y percona-xtrabackup-80
```

**坑 2：依赖报错 `需要 libmysqlclient.so.18()(64bit)`** — xtrabackup 需要 MySQL 5.x 兼容库，系统装的是 MySQL 8，yum 想用 mariadb-libs 顶替却冲突。装 MySQL 官方兼容库 `mysql-community-libs-compat`。但手册 Day1-2 配的阿里云路径已 404，改用静态 RPM 目录，且需 `rpm -ivh --force` 强装（yum 认为已装会跳过，库文件实际没落地）。若 rpm 数据库有重复残留记录，先 `rpm -e --allmatches --nodeps mysql-community-libs-compat` 删干净再装。

**坑 3：`There are unfinished transactions remaining`** — 多次 `Ctrl+C` 中断 yum 导致 rpm 数据库不一致，先 `yum-complete-transaction --cleanup-only` 清理。

**坑 4：下载到的是错误页** — `curl` 官方源或腾讯云镜像时，若 `ls -lh` 显示只有几 KB（实测 989B / 7KB，HTTP 200 但 CDN 对虚拟机出口 IP 差异化响应），就是错误页不是 rpm。带 `-fL` 重试仍不行时，**终极方案：Windows 侧下好 43MB 完整包，用 `scp` 推进虚拟机**（走 ssh 通道不经 CDN）。本次即用此法：

```powershell
scp C:/Users/PC/WorkBuddy/2026-11-23-08-57-07/xtrabackup-8.0.35.rpm root@192.168.88.128:/tmp/xtrabackup.rpm
```

```bash
ls -lh /tmp/xtrabackup.rpm                    # 必须约 43M
rpm -ivh --force --nodeps /tmp/xtrabackup.rpm
xtrabackup --version                          # 8.0.35-31
```

**坑 5：命令整段粘贴粘连** — 多条命令一次粘进 SSH 会丢换行粘成乱命令。一次只执行一条，敲一条 → 回车 → 见 `[root@node1 ~]#` → 再下一条。

**坑 6：copy-back 后 `systemctl start mysqld` 失败（`errno 13 - Permission denied`）** — `tail -60 /var/log/mysqld.log` 报 `File './mysql-bin.index' not found (OS errno 13)`。两个原因：① `chown` 因粘连没执行成功；② SELinux（CentOS 7 默认 enforcing）复制来的文件安全上下文不对。一次一条执行：

```bash
chown -R mysql:mysql /var/lib/mysql
setenforce 0
restorecon -R /var/lib/mysql      # 规范做法，修复安全上下文
systemctl start mysqld
```

> **极易复现**：只 `setenforce 0` 不做 `restorecon`，下次开机 SELinux 恢复 enforcing、上下文仍不对，MySQL 必然再次 failed（报 `ERROR 2002 Can't connect through socket`）。所以必须补 `restorecon -R /var/lib/mysql` 才算彻底。

## 3. 操作过程

**第 1 步：安装 XtraBackup**

按坑 1–4 解决源和依赖问题后，`xtrabackup --version` 输出 `8.0.35-31 based on MySQL server 8.0.35` 即成功。

![S30 版本证明](<../mysql-ops/04-xtrabackup/S30-xtrabackup-ver.jpg>)

**第 2 步：全量备份 → 改数据 → 增量备份**

```bash
mkdir -p /backup/full /backup/inc1
xtrabackup --backup --target-dir=/backup/full -uroot -pNewPass@123
mysql -uroot -pNewPass@123 -e "USE testdb; INSERT INTO t1 VALUES(4,'d'),(5,'e');"    -- 制造差异
xtrabackup --backup --target-dir=/backup/inc1 --incremental-basedir=/backup/full -uroot -pNewPass@123
```

两条备份都输出 `completed OK!`。截图取结尾的 `completed OK!` + 提示符即可，不用截中间刷屏。

![S31 全量备份 OK](<../mysql-ops/04-xtrabackup/S31-full-backup-ok.jpg>)

![S32 增量备份 OK](<../mysql-ops/04-xtrabackup/S32-inc-backup-ok.jpg>)

**第 3 步：prepare（送命题，务必理解原理）**

```bash
xtrabackup --prepare --apply-log-only --target-dir=/backup/full
xtrabackup --prepare --apply-log-only --target-dir=/backup/full --incremental-dir=/backup/inc1
xtrabackup --prepare --target-dir=/backup/full     # 最后一次不加 --apply-log-only，回滚收尾
```

**`--apply-log-only` 原理（必须能讲）**：增量 prepare 时加这个参数是**跳过回滚阶段**——因为未提交的事务可能在下一个增量备份里才提交，提前回滚会把后面的增量全废掉。只有最后一个增量 prepare 完，才做一次不加该参数的完整 prepare 来回滚未提交事务。

![S33 prepare OK](<../mysql-ops/04-xtrabackup/S33-prepare-ok.jpg>)

**第 4 步：恢复（先把原数据挪走，别直接删）**

```bash
systemctl stop mysqld
mv /var/lib/mysql /var/lib/mysql.bak       # 保留现场，出事能回退
mkdir /var/lib/mysql
xtrabackup --copy-back --target-dir=/backup/full
chown -R mysql:mysql /var/lib/mysql         # 不改权限必启动失败
systemctl start mysqld
mysql -uroot -pNewPass@123 -e "SELECT * FROM testdb.t1;"   -- 预期 1-5 全在
```

`copy-back` 三前提（面试会问）：MySQL 已停止、datadir 为空、之后必须 `chown`。

![S34 copy-back OK](<../mysql-ops/04-xtrabackup/S34-copy-back-ok.jpg>)

恢复后 `SELECT *` 显示 1–5，增量数据 4,d / 5,e 都在：

![S35 恢复结果 1-5](<../mysql-ops/04-xtrabackup/S35-xtra-result.jpg>)

![S36 chown + 服务 active](<../mysql-ops/04-xtrabackup/S36-xtra-chown-status.jpg>)

## 4. 关键概念说明（面试重点）

**① XtraBackup 为什么比 mysqldump 快**

物理备份直接复制数据文件，不经过 SQL 层逐行导出/导入，大库（几十 GB 以上）优势明显；且备份期间不锁 InnoDB 表（通过 redo log 抓取一致性）。

**② `--apply-log-only` 的作用**

见第 3 步原理：增量 prepare 跳过回滚，防止未提交事务在下个增量里提交时被提前回滚破坏。最后一轮才做完整 prepare 收尾。

**③ copy-back 三前提**

停库、清空 datadir、改属主为 mysql。少一个都启动失败。

**④ SELinux 与 errno 13**

CentOS 7 默认 enforcing，copy-back 复制来的文件安全上下文不对，mysqld 无权读。`setenforce 0` 只是临时绕过，`restorecon -R /var/lib/mysql` 才是规范修复。

## 5. 复盘 / 面试怎么讲

> 我用 XtraBackup 做了全量 + 增量备份恢复。先全量备份到 `/backup/full`，插入两条数据做差异，再以全量为 `--incremental-basedir` 做增量备份到 `/backup/inc1`。
>
> prepare 分三步：全量和增量都加 `--apply-log-only` 跳过回滚，因为未提交事务可能在下一个增量里才提交，提前回滚会破坏后续增量；最后一个增量 prepare 完再做一次不加参数的完整 prepare 回滚收尾。
>
> 恢复时先停库、把原 datadir 挪走备份、copy-back 后改 mysql 属主再启动，验证 1–5 全在、增量数据也在。
>
> 安装阶段踩了几个国内环境的典型坑：Percona 源卡死（%post 联网脚本）、缺 `libmysqlclient.so.18` 兼容库、yum 未完成事务、CDN 下载到错误页——最后在 Windows 侧下好完整 43MB 包用 scp 推进去才装上。恢复阶段又遇到 errno 13 权限问题，根因是 SELinux 安全上下文，补了 `restorecon` 才彻底解决（只 setenforce 0 下次开机还会失败）。这些现象、原因和解法我都能讲清。
