# 🐧 Ubuntu常用命令速查手册

## 目录
1. [文件和目录操作](#1-文件和目录操作)
2. [文件内容查看](#2-文件内容查看)
3. [文件权限](#3-文件权限)
4. [系统管理](#4-系统管理)
5. [软件包管理](#5-软件包管理)
6. [网络操作](#6-网络操作)
7. [进程管理](#7-进程管理)
8. [用户管理](#8-用户管理)
9. [磁盘管理](#9-磁盘管理)
10. [文本编辑](#10-文本编辑)
11. [压缩解压](#11-压缩解压)
12. [Git操作](#12-git操作)
13. [Python相关](#13-python相关)
14. [WSL相关](#14-wsl相关)
15. [快捷键](#15-快捷键)

---

## 1. 文件和目录操作

| 命令 | 说明 | 示例 |
|------|------|------|
| `pwd` | 显示当前目录 | `pwd` |
| `ls` | 列出目录内容 | `ls -la` |
| `cd` | 切换目录 | `cd /home/user` |
| `mkdir` | 创建目录 | `mkdir -p dir/subdir` |
| `rmdir` | 删除空目录 | `rmdir dir` |
| `touch` | 创建空文件 | `touch file.txt` |
| `cp` | 复制文件 | `cp file.txt newfile.txt` |
| `mv` | 移动/重命名 | `mv old.txt new.txt` |
| `rm` | 删除文件 | `rm -rf dir` |
| `find` | 查找文件 | `find . -name "*.py"` |
| `ln` | 创建链接 | `ln -s target link` |

**常用选项：**
- `ls -la`: 显示所有文件（包括隐藏）和详细信息
- `cp -r`: 递归复制目录
- `rm -r`: 递归删除目录
- `rm -f`: 强制删除，不提示

---

## 2. 文件内容查看

| 命令 | 说明 | 示例 |
|------|------|------|
| `cat` | 查看文件内容 | `cat file.txt` |
| `less` | 分页查看 | `less file.txt` |
| `head` | 查看开头 | `head -n 10 file.txt` |
| `tail` | 查看末尾 | `tail -n 10 file.txt` |
| `grep` | 搜索内容 | `grep "keyword" file.txt` |
| `wc` | 统计字数 | `wc -l file.txt` |
| `diff` | 比较文件 | `diff file1.txt file2.txt` |

**常用选项：**
- `grep -r`: 递归搜索目录
- `grep -i`: 忽略大小写
- `grep -n`: 显示行号
- `tail -f`: 实时跟踪文件变化

---

## 3. 文件权限

| 命令 | 说明 | 示例 |
|------|------|------|
| `chmod` | 修改权限 | `chmod 755 file.sh` |
| `chown` | 修改所有者 | `chown user:group file.txt` |
| `chgrp` | 修改组 | `chgrp group file.txt` |

**权限说明：**
- `r` (读) = 4
- `w` (写) = 2  
- `x` (执行) = 1
- `chmod 755`: 所有者全部权限，其他用户读和执行

---

## 4. 系统管理

| 命令 | 说明 | 示例 |
|------|------|------|
| `date` | 显示日期时间 | `date` |
| `cal` | 显示日历 | `cal` |
| `uptime` | 系统运行时间 | `uptime` |
| `who` | 当前登录用户 | `who` |
| `uname` | 系统信息 | `uname -a` |
| `df` | 磁盘空间 | `df -h` |
| `free` | 内存使用 | `free -h` |
| `top` | 进程监控 | `top` |
| `htop` | 高级进程监控 | `htop` |
| `history` | 命令历史 | `history` |
| `clear` | 清屏 | `clear` |

---

## 5. 软件包管理

| 命令 | 说明 | 示例 |
|------|------|------|
| `apt-get update` | 更新软件源 | `sudo apt-get update` |
| `apt-get upgrade` | 升级软件包 | `sudo apt-get upgrade` |
| `apt-get install` | 安装软件 | `sudo apt-get install vim` |
| `apt-get remove` | 删除软件 | `sudo apt-get remove vim` |
| `apt-get autoremove` | 清理无用依赖 | `sudo apt-get autoremove` |
| `apt-cache search` | 搜索软件 | `apt-cache search python` |
| `apt-cache show` | 查看软件信息 | `apt-cache show python3` |

**常用PPA源示例：**
```bash
# 添加PPA源
sudo add-apt-repository ppa:ppa-name/ppa

# 更新并安装软件
sudo apt-get update && sudo apt-get install package-name
```

---

## 6. 网络操作

| 命令 | 说明 | 示例 |
|------|------|------|
| `ifconfig` | 网络接口信息 | `ifconfig` |
| `ip` | 网络配置 | `ip addr` |
| `ping` | 测试连通性 | `ping google.com` |
| `curl` | 下载/测试 | `curl http://example.com` |
| `wget` | 下载文件 | `wget https://example.com/file.zip` |
| `ssh` | 远程登录 | `ssh user@host` |
| `scp` | 远程复制 | `scp file.txt user@host:/path` |
| `netstat` | 网络状态 | `netstat -tuln` |

---

## 7. 进程管理

| 命令 | 说明 | 示例 |
|------|------|------|
| `ps` | 查看进程 | `ps aux` |
| `kill` | 终止进程 | `kill PID` |
| `killall` | 终止同名进程 | `killall firefox` |
| `pkill` | 按名称终止进程 | `pkill -f python` |
| `nohup` | 后台运行 | `nohup python train.py &` |
| `jobs` | 查看后台任务 | `jobs` |
| `fg` | 前台运行 | `fg %1` |
| `bg` | 后台运行 | `bg %1` |

---

## 8. 用户管理

| 命令 | 说明 | 示例 |
|------|------|------|
| `whoami` | 当前用户 | `whoami` |
| `adduser` | 添加用户 | `sudo adduser newuser` |
| `deluser` | 删除用户 | `sudo deluser user` |
| `passwd` | 修改密码 | `passwd` |
| `su` | 切换用户 | `su root` |
| `sudo` | 以root执行 | `sudo apt-get update` |
| `groups` | 用户组 | `groups username` |

---

## 9. 磁盘管理

| 命令 | 说明 | 示例 |
|------|------|------|
| `df` | 磁盘空间 | `df -h` |
| `du` | 目录大小 | `du -sh dir` |
| `mount` | 挂载设备 | `sudo mount /dev/sda1 /mnt` |
| `umount` | 卸载设备 | `sudo umount /mnt` |
| `fdisk` | 磁盘分区 | `sudo fdisk -l` |

---

## 10. 文本编辑

### Vim编辑器

| 命令 | 说明 |
|------|------|
| `vim file.txt` | 打开文件 |
| `i` | 进入插入模式 |
| `Esc` | 退出插入模式 |
| `:w` | 保存 |
| `:q` | 退出 |
| `:wq` | 保存并退出 |
| `:q!` | 强制退出（不保存） |
| `/keyword` | 搜索 |
| `dd` | 删除一行 |
| `yy` | 复制一行 |
| `p` | 粘贴 |

### Nano编辑器

| 命令 | 说明 |
|------|------|
| `nano file.txt` | 打开文件 |
| `Ctrl+O` | 保存 |
| `Ctrl+X` | 退出 |
| `Ctrl+W` | 搜索 |

---

## 11. 压缩解压

| 命令 | 说明 | 示例 |
|------|------|------|
| `tar` | 打包压缩 | `tar -czvf archive.tar.gz dir/` |
| `tar` | 解压 | `tar -xzvf archive.tar.gz` |
| `zip` | ZIP压缩 | `zip archive.zip file1.txt file2.txt` |
| `unzip` | ZIP解压 | `unzip archive.zip` |
| `gzip` | GZ压缩 | `gzip file.txt` |
| `gunzip` | GZ解压 | `gunzip file.txt.gz` |

**常用选项：**
- `-c`: 创建
- `-x`: 解压
- `-z`: gzip压缩
- `-v`: 详细输出
- `-f`: 指定文件名

---

## 12. Git操作

| 命令 | 说明 | 示例 |
|------|------|------|
| `git init` | 初始化仓库 | `git init` |
| `git clone` | 克隆仓库 | `git clone https://github.com/user/repo.git` |
| `git add` | 添加文件 | `git add .` |
| `git commit` | 提交 | `git commit -m "message"` |
| `git push` | 推送 | `git push origin main` |
| `git pull` | 拉取 | `git pull origin main` |
| `git status` | 状态 | `git status` |
| `git log` | 日志 | `git log` |
| `git branch` | 分支 | `git branch -a` |
| `git checkout` | 切换分支 | `git checkout feature` |

---

## 13. Python相关

| 命令 | 说明 | 示例 |
|------|------|------|
| `python3 --version` | 版本信息 | `python3 --version` |
| `python3 -m venv` | 创建虚拟环境 | `python3 -m venv venv` |
| `source venv/bin/activate` | 激活虚拟环境 | `source venv/bin/activate` |
| `deactivate` | 退出虚拟环境 | `deactivate` |
| `pip install` | 安装包 | `pip install numpy` |
| `pip list` | 已安装包 | `pip list` |
| `pip freeze` | 导出依赖 | `pip freeze > requirements.txt` |
| `pip install -r` | 安装依赖 | `pip install -r requirements.txt` |

---

## 14. WSL相关

| 命令 | 说明 | 示例 |
|------|------|------|
| `wsl --list` | 列出发行版 | `wsl --list --verbose` |
| `wsl --shutdown` | 关闭WSL | `wsl --shutdown` |
| `wsl --export` | 导出发行版 | `wsl --export Ubuntu-24.04 backup.tar` |
| `wsl --import` | 导入发行版 | `wsl --import Ubuntu-24.04 D:\WSL\Ubuntu backup.tar` |
| `wsl -d` | 指定发行版 | `wsl -d Ubuntu-24.04` |
| `wsl --set-default` | 设置默认发行版 | `wsl --set-default Ubuntu-24.04` |

---

## 15. 快捷键

| 快捷键 | 说明 |
|--------|------|
| `Ctrl+C` | 终止当前命令 |
| `Ctrl+D` | 退出终端 |
| `Ctrl+L` | 清屏 |
| `Ctrl+A` | 光标移到行首 |
| `Ctrl+E` | 光标移到行尾 |
| `Ctrl+U` | 删除光标前内容 |
| `Ctrl+K` | 删除光标后内容 |
| `Ctrl+W` | 删除光标前单词 |
| `Tab` | 自动补全 |
| `↑/↓` | 上下浏览命令历史 |
| `!!` | 执行上一条命令 |
| `!keyword` | 执行最近的keyword命令 |

---

## 📝 常用别名建议

在 `~/.bashrc` 中添加别名：

```bash
# 常用别名
alias ls='ls -la'
alias ll='ls -lh'
alias ..='cd ..'
alias ...='cd ../..'
alias grep='grep --color=auto'
alias python='python3'
alias pip='pip3'
```

---

## 📚 参考资源

- [Ubuntu官方文档](https://help.ubuntu.com/)
- [Linux命令大全](https://man.linuxde.net/)
- [WSL文档](https://docs.microsoft.com/zh-cn/windows/wsl/)

---

*文档版本: v1.0*  
*生成日期: 2026-05-25*  
*项目位置: `docs/ubuntu_commands.md`*
