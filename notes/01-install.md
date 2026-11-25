# 01 MySQL 8.0 在 CentOS 7 上的安装与初始化

## 1. 实验环境
- VMware Workstation + CentOS 7.9（最小安装，2GB 内存 / 40GB 磁盘，NAT）
- MySQL 8.0（阿里云 yum 源安装）
- 截图：S05/S06/S07

## 2. 问题现象（这节写"踩坑"，是博客素材）
- CentOS 7 已 EOL，官方源失效 → 换阿里云 vault 源（贴 S07）
- dev.mysql.com 下载超时 → 换阿里云 MySQL 源
- 启动失败时查 /var/log/mysqld.log

## 3. 排查/安装过程
（贴 3.3/3.4 的关键命令 + 输出截图 S08/S09）

## 4. 配置说明（面试重点）
- 逐条解释 my.cnf：datadir / utf8mb4 / 时区 / max_connections / innodb_buffer_pool_size
- 贴 S11

## 5. 验证结果
- SHOW VARIABLES LIKE 'version%'（贴 S10）
- 远程连接与防火墙（贴 S12/S13）

## 6. 复盘 / 面试怎么讲
"我在 CentOS 7 上用阿里云 yum 源装的 MySQL 8.0，改了 my.cnf 的字符集、时区、缓冲池，开了远程和防火墙。缓冲池是 InnoDB 缓存数据和索引的内存区，设太大挤占系统内存、太小磁盘 IO 多。"
