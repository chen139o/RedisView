# Redis Viewer

一个基于Python和PyQt5的可视化Redis数据查看工具，类似Another Redis Desktop Manager。

## 功能特性

1. **查看数据** - 浏览Redis中的所有键，并查看对应的值
2. **自定义数据转换** - 支持多种数据格式转换：
   - Base64 编码/解码
   - Gzip 压缩/解压
   - Snappy 压缩/解压
   - Zstandard 压缩/解压
   - JSON 格式化（美化/压缩）
3. **数据复制粘贴** - 支持复制数据到剪贴板和从剪贴板粘贴数据
4. **Redis命令执行** - 支持直接执行Redis命令
5. **用户友好界面** - 直观的图形界面，易于操作

## 安装和使用

### 方法1：使用标准启动脚本

1. 需要创建虚拟环境
2. 双击运行 `start.bat` 脚本
3. 脚本会自动激活虚拟环境并启动Redis Viewer
4. 会显示终端窗口（用于调试目的）

### 方法2：手动运行

1. 启动Redis Viewer：

   ```
   python redis_viewer.py
   ```

## 使用说明

### 连接Redis

1. 点击菜单栏的 `File` -> `Connect`
2. 在弹出的连接对话框中输入Redis服务器信息：
   - Host: Redis服务器地址（默认为localhost）
   - Port: Redis端口号（默认为6379）
   - Password: Redis密码（如果有）
   - Database: 数据库编号（默认为0）
3. 点击 `Connect` 按钮连接到Redis服务器

### 查看数据

1. 连接成功后，左侧会显示Redis中的所有键
2. 点击任意键，右侧会显示对应的值
3. 可以使用搜索框过滤键名
4. 点击"Refresh"按钮刷新键列表

### 数据转换

1. 在右侧数据标签页中，选择需要的数据转换方式
2. 点击"Apply"按钮应用转换
3. 转换后的结果会显示在文本框中

### 数据操作

- **复制数据**：选中要复制的文本，使用快捷键 `Ctrl+C` 或点击"Copy Data"按钮
- **粘贴数据**：选择一个键后，使用快捷键 `Ctrl+V` 或点击"Paste Data"按钮
- **保存数据**：修改数据后，点击"Save Data"按钮保存到Redis
  - **修改Key/TTL**：点击"Modify Key/TTL"按钮可以重命名key或设置/修改TTL值
  - **转换链历史**：点击"Chain History"按钮可以查看和重用之前的转换链
  - **自动连接**：在连接对话框中勾选"Auto-connect on startup"可实现自动连接

### 执行Redis命令

1. 切换到"Commands"标签页
2. 在输入框中输入Redis命令（如：`SET mykey "hello"`）
3. 按下回车键或点击"Execute"按钮执行命令
4. 命令执行结果会显示在下方的输出区域

## 技术栈

- Python 3.13
- PyQt5 - GUI框架
- redis - Redis客户端
- pybase64 - Base64编码/解码
- python-snappy - Snappy压缩/解压
- zstandard - Zstandard压缩/解压
- gzip - Gzip压缩/解压（Python标准库）
- json - JSON处理（Python标准库）

## 注意事项

1. 程序启动时会自动加载同目录下的 `redis_icon.png` 文件作为窗口图标
2. 本工具使用虚拟Python环境，不会影响系统自带的Python
3. 当前版本主要支持字符串类型的键值查看，其他类型将显示类型信息
4. 建议使用最新版本的Redis服务器
5. 如果遇到连接问题，请检查Redis服务器的防火墙设置

## 开发说明

如果需要修改或扩展功能，可以：

1. 激活虚拟环境
2. 修改 `redis_viewer.py` 文件
3. 重新运行应用程序测试

