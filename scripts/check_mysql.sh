#!/bin/bash
# check_mysql.sh —— MySQL 运维监控脚本（实验 8 产出）
# 检查项：磁盘使用率 / 连接数 / 慢查询数，超阈值写入告警日志
# 用法：bash check_mysql.sh   （建议加 crontab 定时执行，见 README）

MYSQL_USER="root"
MYSQL_PASS="NewPass@123"
LOG="/var/log/mysql_alert.log"
DATA_DIR="/var/lib/mysql"

# 阈值（可按生产环境调整）
DISK_WARN=80      # 磁盘使用率 %
CONN_WARN=150     # 连接数
SLOW_WARN=50      # 慢查询条数（近 1 分钟）

log_alert() {
    echo "$(date '+%Y-%m-%d %H:%M:%S')  [WARN]  $1" >> "$LOG"
}

# 1. 磁盘使用率（取数据目录所在分区的 Use%）
DISK=$(df -h "$DATA_DIR" | awk 'NR==2{gsub("%","",$5);print $5}')
if [ "$DISK" -ge "$DISK_WARN" ]; then
    log_alert "磁盘使用率 ${DISK}% (阈值 ${DISK_WARN}%)  分区: $DATA_DIR"
fi

# 2. 当前连接数
CONN=$(mysql -u"$MYSQL_USER" -p"$MYSQL_PASS" -N -e "SHOW STATUS LIKE 'Threads_connected';" 2>/dev/null | awk '{print $2}')
if [ -n "$CONN" ] && [ "$CONN" -ge "$CONN_WARN" ]; then
    log_alert "当前连接数 ${CONN} (阈值 ${CONN_WARN})"
fi

# 3. 慢查询数（近 1 分钟，需已开启 slow_query_log）
SLOW=$(mysql -u"$MYSQL_USER" -p"$MYSQL_PASS" -N -e "SHOW GLOBAL STATUS LIKE 'Slow_queries';" 2>/dev/null | awk '{print $2}')
if [ -n "$SLOW" ] && [ "$SLOW" -ge "$SLOW_WARN" ]; then
    log_alert "慢查询累计数 ${SLOW} (阈值 ${SLOW_WARN})"
fi

# 4. 一切正常也写一条心跳，证明脚本在跑
echo "$(date '+%Y-%m-%d %H:%M:%S')  [OK]  disk=${DISK}% conn=${CONN:-N/A} slow=${SLOW:-N/A}" >> "$LOG"
