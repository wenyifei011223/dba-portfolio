# 笔记 08：磁盘告警与连接数打满故障演练

> 状态：**模板（待实测填充）**。实验 8 属手册标注的"可压缩"项，前 7 个实验完成后补做。
> 实测时把真实报错原文贴进【实测证据】段，截图存 `mysql-ops/08-fault-drill/`。

## 一、环境

- VMware Workstation + CentOS 7 + MySQL 8.0.43
- 所有故障演练**只在虚拟机 node1 做**，不碰宿主机
- 连接密码：`NewPass@123`

## 二、踩坑记录

（实测后补充，例如：`fallocate` 填满分区后 MySQL 报什么错、KILL 连接时的权限问题等）

## 三、操作过程

### 3.1 监控脚本

写 `scripts/check_mysql.sh`，检查三项：磁盘使用率、连接数、慢查询数，超阈值写 `/var/log/mysql_alert.log`。
部署并跑一次：

```bash
chmod +x scripts/check_mysql.sh
bash scripts/check_mysql.sh
cat /var/log/mysql_alert.log
```

**截图**：S58-monitor-script.png（能看到日志中的 `[OK]` 心跳行）。

> 生产用法：加入 crontab 每 5 分钟跑一次
> `*/5 * * * * /bin/bash /path/to/check_mysql.sh`

### 3.2 磁盘打满故障

```bash
fallocate -l 20G /tmp/bigfile                       # 只在虚拟机！
mysql -uroot -pNewPass@123 -e "INSERT INTO sbtest.sbtest1(k,c,pad) VALUES(1,'x','y');"
du -sh /var/lib/mysql/* | sort -h | tail
rm -f /tmp/bigfile
mysql -uroot -pNewPass@123 -e "PURGE BINARY LOGS BEFORE '2026-11-20';"
mysql -uroot -pNewPass@123 -e "SET GLOBAL binlog_expire_logs_seconds=604800;"
```

**截图**：S59-disk-full.png（`ERROR 1030 ... No space left on device` 原文）。

### 3.3 连接数打满故障

```bash
mysql -uroot -pNewPass@123 -e "SET GLOBAL max_connections=10;"
for i in $(seq 1 20); do mysql -uroot -pNewPass@123 -e "SELECT 1;" & done; wait
mysql -uroot -pNewPass@123 -e "SHOW PROCESSLIST;"
mysql -uroot -pNewPass@123 -e "SET GLOBAL max_connections=200;"
```

**截图**：S60-too-many-connections.png（`ERROR 1040 ... Too many connections` 原文）。

## 四、【实测证据】（待填充）

- 磁盘满报错原文：
- 连接打满报错原文：
- `SHOW PROCESSLIST` 看到的来源：
- 告警日志内容：

## 五、面试重点

| 追问 | 要点 |
|---|---|
| 线上磁盘满的常见原因？ | binlog 堆积、慢日志未清理、临时文件、ibdata1 膨胀、误写大文件 |
| 磁盘满怎么应急？ | 先 `df -h` 定位分区 → `du -sh` 找大文件 → 确认是 binlog 就 `PURGE` → 配 `binlog_expire_logs_seconds` → 永不手删 `.ibd` |
| 连接打满怎么应急？ | 限流 → `SHOW PROCESSLIST` 找来源 IP/用户 → `KILL` 异常连接 → 调 `max_connections` → 排查慢查询根因 |
| 有没有做过监控？ | 拿出 `scripts/check_mysql.sh`，说清三项阈值和 crontab 部署 |

## 六、30 秒话术

> "我在虚拟机上复现过两类线上常见故障：用 fallocate 撑满数据盘，MySQL 写入直接报 1030 No space left，我用 du 定位到 binlog 堆积，PURGE 后配置 7 天自动过期恢复；又把 max_connections 调到 10，并发连上去触发 1040 Too many connections，SHOW PROCESSLIST 找到来源连接 KILL 掉再调回参数。此外我写了个 check_mysql.sh 监控脚本，检查磁盘、连接数、慢查询三项，超阈值写告警日志，可以挂 crontab 定时跑。"
