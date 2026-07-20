# DouYinSparkAI

抖音智能续火花 —— 自动检测好友消息，AI 生成个性化回复，火花永不断。

## 工作原理

1. 通过 Playwright 无头浏览器登录抖音创作者中心网页版
2. 打开与目标好友的聊天窗口，读取最近消息
3. 如果今天已经发过消息 → 跳过（不重复发）
4. 如果对方发了视频 → 提取视频标题/描述作为上下文
5. 调用 AI 根据上下文生成自然回复
6. 发送回复，完成续火花

---

## 部署方式一：GitHub Actions 自动部署（推荐）

配置一次，之后每天自动运行，无需维护服务器。

### 第一步：创建仓库并推送代码

在 GitHub 新建一个**空仓库**（不勾选 README/gitignore），然后：

```bash
git remote add origin https://github.com/你的用户名/你的仓库名.git
git push -u origin main
```

### 第二步：获取抖音 Cookie

1. 电脑浏览器打开 https://creator.douyin.com/ 并登录
2. F12 → Application → Cookies → `https://creator.douyin.com`
3. 用 EditThisCookie 等插件导出 JSON 格式（或手动复制）

> Cookie 有效期约 1-3 个月，过期后重新获取并更新 Secret 即可。

### 第三步：配置 GitHub Environment

进入仓库：**Settings → Secrets and variables → Actions → Environments → New environment**，名称填 `user-data`。

**Environment secrets：**

| 名称 | 内容 |
|------|------|
| `AI_API_KEY` | AI 接口密钥（如 DeepSeek 的 sk-xxx） |
| `COOKIES_USER1` | 抖音 Cookie JSON |

**Environment variables：**

| 名称 | 内容 | 示例 |
|------|------|------|
| `TASKS` | 任务列表 JSON | 见下方格式 |
| `AI_PROVIDER` | API 格式 | `openai` 或 `anthropic` |
| `AI_BASE_URL` | API 请求地址 | `https://api.deepseek.com` |
| `AI_MODEL` | 模型名 | `deepseek-chat` |
| `MATCH_MODE` | 好友匹配方式 | `nickname`（默认）或 `short_id` |

### 第四步：填写 TASKS

```json
[
  {
    "username": "我的抖音昵称",
    "unique_id": "user1",
    "targets": ["好友A", "好友B"]
  }
]
```

- `unique_id` 决定 Cookie 变量名：`user1` → 对应 `COOKIES_USER1`（自动转大写）
- `targets` 填好友列表里显示的名字：有备注填备注，没备注填对方昵称。`MATCH_MODE=short_id` 时填抖音号
- 多账号：添加多个对象，每个配对应的 `COOKIES_XXX`

### 第五步：启用并测试

1. 进入仓库 **Actions** 页面，启用 workflow
2. 点 "Run workflow" 手动跑一次，确认日志正常
3. 搞定。之后每天北京时间 9:00 自动续火花

### 修改运行时间（可选）

编辑 `.github/workflows/schedule.yml`：

```yaml
cron: "0 1 * * *"  # UTC 时间，北京时间 = UTC + 8
```

示例：`30 13 * * *` = 北京 21:30，`0 22 * * *` = 北京次日 6:00。

---

## 部署方式二：手动部署（本地 / 服务器）

适合想自己控制运行时间、或没有 GitHub 账号的用户。

### 环境要求

- Python 3.9+
- 能访问抖音创作者中心的网络环境

### 安装

```bash
git clone https://github.com/你的用户名/你的仓库名.git
cd DouYinSparkAI
pip install -r requirements.txt
playwright install chromium
```

### 配置环境变量

```bash
export TASKS='[{"username":"我","unique_id":"user1","targets":["好友A"]}]'
export COOKIES_USER1='[...你的 cookie json...]'
export AI_PROVIDER='openai'
export AI_API_KEY='sk-xxx'
export AI_BASE_URL='https://api.deepseek.com'
export AI_MODEL='deepseek-chat'
export LOG_LEVEL='INFO'
```

本地调试时可加 `export HEADLESS='false'` 看到浏览器操作过程。

### 运行

```bash
python main.py
```

### 定时执行

**Linux / macOS（crontab）：**

```bash
crontab -e
# 每天北京时间 9:00 执行
0 9 * * * cd /path/to/DouYinSparkAI && /usr/bin/python3 main.py >> logs/cron.log 2>&1
```

**Windows（任务计划程序）：**

创建基本任务 → 每日触发 → 操作填 `python main.py`，起始目录填项目路径。

**Docker（可选）：**

```bash
docker run --rm \
  -e TASKS='[...]' \
  -e COOKIES_USER1='[...]' \
  -e AI_API_KEY='sk-xxx' \
  -e AI_BASE_URL='https://api.deepseek.com' \
  -e AI_MODEL='deepseek-chat' \
  $(docker build -q .)
```

> 需自行编写 Dockerfile，基础镜像用 `mcr.microsoft.com/playwright/python:v1.40.0-jammy`。

---

## AI 配置说明

通过 `AI_PROVIDER` 切换 API 格式：

### OpenAI 兼容格式（默认）

`AI_PROVIDER=openai`（或不填）。适用于所有 `/v1/chat/completions` 接口：

| 服务商 | AI_BASE_URL | AI_MODEL |
|--------|-------------|----------|
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-turbo` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| 中转站 | 填中转站给的 base url | 填对应模型名 |
| 本地 Ollama | `http://localhost:11434/v1` | 自定义 |

### Anthropic 格式

`AI_PROVIDER=anthropic`。适用于 Anthropic 官方或兼容中转站：

| 场景 | AI_BASE_URL | AI_MODEL |
|------|-------------|----------|
| 官方 | 留空 | `claude-sonnet-4-20250514` |
| 中转站 | 填中转站地址 | 填对应模型名 |

### 中转站怎么填？

看中转站文档说兼容哪种格式：
- "兼容 OpenAI" → `AI_PROVIDER=openai` + 填它的 base url
- "兼容 Anthropic" → `AI_PROVIDER=anthropic` + 填它的地址
- 两种都支持选 `openai`，兼容性更广

---

## FAQ

**Q: API Key 放 GitHub 上安全吗？**

安全。GitHub Secrets 加密存储，运行时才注入环境变量，不出现在日志、代码或任何公开页面。即使仓库 public 别人也看不到。别把 key 写进代码 commit 就行。

**Q: 用中转站安全吗？**

取决于中转站可信度。聊天上下文会经过中转站服务器。介意隐私就用 DeepSeek / 通义千问官方 API，本身很便宜。

**Q: 每天花多少钱？**

极少。每次约 100-200 token。DeepSeek 价格下 5 个好友跑一个月不到 ¥0.1。Anthropic 贵些也就几毛。

**Q: Cookie 过期了怎么办？**

Actions 会失败（日志有提示）。重新登录创作者中心 → 导出 Cookie → 更新 Secret。

**Q: 会被封号吗？**

每天每个好友一条消息，和正常使用无异。但任何自动化都有理论风险，建议少量好友使用。

**Q: 对方发的视频 AI 能看懂吗？**

目前提取视频卡片上的标题/描述文字给 AI 参考，不是真正"看"视频。没有文字信息时发通用问候。

**Q: 支持多账号吗？**

支持。TASKS 里加多个对象，每个配对应 `COOKIES_XXX`。

**Q: 为什么用创作者中心而不是 APP？**

APP 自动化需 root/越狱，门槛高风险大。网页版天然支持私信，Playwright 更稳定。

**Q: Actions 突然不跑了？**

GitHub 60 天无活动会禁用 workflow。本项目内置 keepalive 保活。如果还不行去 Actions 页面 re-enable。

---

## 注意事项

- 抖音网页版存在 A/B 测试，不同账号 DOM 不同，代码已做多版本选择器兼容
- 运行失败先下载 Actions 的 logs artifact 排查
- 本项目仅供学习研究，使用风险自行承担

## License

MIT
