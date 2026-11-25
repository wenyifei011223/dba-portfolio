# 01 MySQL 8.0 在 CentOS 7 上的安装与初始化

## 1. 实验环境

- VMware Workstation 17.5.2 + CentOS 7.9（最小安装，8GB 内存 / 50GB 磁盘 / 4 核，NAT，IP 192.168.88.128）
- MySQL 8.0.43（清华 yum 源安装）
- 系统 root 与 MySQL root 密码均设为 root（仅本地实验，生产环境禁止弱密码）

## 2. 问题现象（踩坑记录）

CentOS 7 EOL 后装 MySQL，网上多数教程的地址都已失效，这是本篇最有价值的部分。

**坑 1：CentOS 7 官方源失效** — yum install 报 `Could not resolve host / cannot find a valid baseurl`。原因是 CentOS 7 于 2024 年停止维护，官方 mirrorlist 下线。换成阿里云 vault 归档源，旧 repo 先备份到 bak/。成功标志是 `yum makecache` 出现 `Metadata Cache Created`。

![S07 yum 源重建缓存](<../mysql-ops/00-environment/S07-CentOS 7 换 yum 源.jpg>)

**坑 2：教程里的阿里云 MySQL 源也是 404** — 配好 `mirrors.aliyun.com/mysql/yum/...` 后报 `curl: (22) 404`。用 `curl -s -o /dev/null -w "%{http_code}"` 逐个测，发现 baseurl 和 gpgkey 两个地址都失效。baseurl 换成清华源 `mirrors.tuna.tsinghua.edu.cn/mysql/yum/mysql80-community-el7/`，gpgkey 改用 MySQL 官方地址。

**坑 3：GPG key 版本不匹配** — 装包时报 `NOKEY, key ID a8d3785c`，签名验证失败。包是用 2023 年的密钥签的，导入的却是 2022 的 key。改成 `rpm --import https://repo.mysql.com/RPM-GPG-KEY-mysql-2023` 后正常。

**坑 4：mariadb 残留冲突** — `rpm -qa | grep -i mariadb` 查出 `mariadb-libs-1:5.5.68`，需先 `rpm -e --nodeps mariadb-libs`。

**坑 5：临时密码反复输错** — `ERROR 1045 (using password: YES/NO)`。原因：把文档里的占位符 `xxxx` 当密码输了；中文输入法下 `!` 变全角且屏幕不回显，看不出输错。切英文输入法手敲解决。

## 3. 安装过程

```bash
# 换源：备份 + 写阿里云 vault
mkdir -p /etc/yum.repos.d/bak
mv /etc/yum.repos.d/*.repo /etc/yum.repos.d/bak/
cat > /etc/yum.repos.d/CentOS-vault.repo << 'EOF'
[base]
name=CentOS-7.9.2009 - base - Aliyun vault
baseurl=https://mirrors.aliyun.com/centos-vault/7.9.2009/os/$basearch/
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7
EOF
yum clean all && yum makecache

# 配 MySQL 源 + 装包 + 启动
rpm -e --nodeps mariadb-libs
cat > /etc/yum.repos.d/mysql-community.repo << 'EOF'
[mysql80-community]
name=MySQL 8.0 Community Server
baseurl=https://mirrors.tuna.tsinghua.edu.cn/mysql/yum/mysql80-community-el7/
enabled=1
gpgcheck=1
gpgkey=https://repo.mysql.com/RPM-GPG-KEY-mysql-2023
EOF
rpm --import https://repo.mysql.com/RPM-GPG-KEY-mysql-2023
yum clean all && yum makecache
yum install -y mysql-community-server
systemctl start mysqld && systemctl enable mysqld
```

![S08 服务运行中](<../mysql-ops/00-environment/S08-Mysql安装并启动.jpg>)

改密码（root 是弱密码，需先降策略）：

```bash
grep 'temporary password' /var/log/mysqld.log
mysql -u root -p
SET GLOBAL validate_password.policy = LOW;
SET GLOBAL validate_password.length = 4;
SET GLOBAL validate_password.check_user_name = OFF;
ALTER USER 'root'@'localhost' IDENTIFIED BY 'root';
FLUSH PRIVILEGES;
```

## 4. 配置说明（面试重点）

最终 my.cnf（含第 ⑤ 步加的 bind-address）：

```ini
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
```

| 参数 | 作用 / 面试要点 |
|---|---|
| `bind-address=0.0.0.0` | 监听所有网卡，默认 127.0.0.1 只允许本机，改完要重启 |
| `datadir` | 数据文件目录，表空间和 redo log 都在这里 |
| `socket` | 本机连接走 socket 不走 TCP，更快 |
| `port=3306` | 防火墙要放行这个端口 |
| `character-set-server=utf8mb4` | 真 UTF-8，utf8 只有 3 字节存不了 emoji |
| `collation-server=utf8mb4_0900_ai_ci` | 0900=Unicode 9.0 标准，ai/ci=不区分大小写/重音 |
| `default-time-zone='+8:00'` | 东八区，否则 TIMESTAMP 差 8 小时 |
| `max_connections=200` | 默认 151，太小报 Too many connections，太大耗内存 |
| `innodb_buffer_pool_size=512M` | **最重要**：缓存数据和索引的内存区。太小磁盘 IO 多、查询慢；太大挤占系统内存。生产一般设物理内存的 50%–75% |
| `log-error` | 错误日志，启动失败先看这里 |

![S11 my.cnf 内容](<../mysql-ops/00-environment/S11-my.cnf 文件内容.jpg>)

## 5. 验证结果

```bash
mysql -uroot -proot -e "SHOW VARIABLES LIKE 'version%';"
```

输出 `version = 8.0.43`。

![S10 版本号](<../mysql-ops/00-environment/S10-显示数据库版本.jpg>)

远程与防火墙：

```bash
firewall-cmd --permanent --zone=public --add-port=3306/tcp
firewall-cmd --reload
mysql -h192.168.88.128 -uapp -pApp@123456 -e "SELECT 1;"
```

![S12 防火墙放行](<../mysql-ops/00-environment/S12-防火墙放行.jpg>)
![S13 远程登录](<../mysql-ops/00-environment/S13-验证远程登录.jpg>)

## 6. 复盘 / 面试怎么讲

> 我在 CentOS 7 上用阿里云 vault 源加清华的 MySQL 源装了 MySQL 8.0.43。踩坑主要集中在 EOL 之后的地址失效：官方源、教程里的阿里云 MySQL 源、GPG key 版本、mariadb 残留，基本都是靠 curl 测地址、看 /var/log/mysqld.log 一点点排出来的。
>
> 配置上改了 utf8mb4 字符集、东八区时区、200 最大连接数和 512M 的 InnoDB 缓冲池。缓冲池是 InnoDB 缓存数据和索引的内存区，太大挤占系统内存，太小磁盘 IO 多，生产一般设物理内存的 50%–75%。还开了 bind-address 和防火墙 3306 端口，用 app 用户做了远程连接验证。
