# DouYinSparkAI

抖音智能续火花 —— 自动检测好友消息，AI 生成个性化回复，火花永不断。

## 工作原理

1. 通过 Playwright 无头浏览器登录抖音创作者中心网页版
2. 打开与目标好友的聊天窗口，读取最近消息
3. 如果今天已经发过消息 → 跳过（不重复发）
4. 如果对方发了视频 → 提取视频标题/描述作为上下文
5. 调用 AI 根据上下文生成自然回复
6. 发送回复，完成续火花

## 部署（GitHub Actions）

### 1. 创建仓库

在 GitHub 新建一个**空仓库**（不勾选 README/gitignore），然后把本项目代码推上去：

```bash
git remote add origin https://github.com/你的用户名/你的仓库名.git
git push -u origin main
```

### 2. 获取抖音 Cookie

1. 电脑浏览器打开 https://creator.douyin.com/ 并登录你的抖音账号
2. 按 F12 打开开发者工具 → Application（应用）→ 左侧 Cookies → `https://creator.douyin.com`
3. 全选所有 Cookie，右键复制（或用 EditThisCookie 等插件导出 JSON 格式）

> Cookie 有效期约 1-3 个月，过期后需重新获取。

### 3. 配置 GitHub Environment

进入仓库页面：**Settings → Secrets and variables → Actions → Environments → New environment**

名称必须填 `user-data`（和 workflow 文件对应）。

创建后点进去，分别添加：

**Environment secrets（点 "Add secret"）：**

| 名称 | 内容 |
|------|------|
| `AI_API_KEY` | 你的 AI 接口密钥（如 DeepSeek 的 sk-xxx） |
| `COOKIES_USER1` | 抖音 Cookie 的 JSON 字符串 |

**Environment variables（点 "Add variable"）：**

| 名称 | 内容 | 示例 |
|------|------|------|
| `TASKS` | 任务列表 JSON | 见下方 |
| `AI_PROVIDER` | API 格式 | `openai` 或 `anthropic` |
| `AI_BASE_URL` | API 请求地址 | `https://api.deepseek.com` |
| `AI_MODEL` | 模型名 | `deepseek-chat` |
| `MATCH_MODE` | 好友匹配方式 | `nickname`（默认）或 `short_id` |

### 4. TASKS 格式

```json
[
  {
    "username": "我的抖音昵称",
    "unique_id": "user1",
    "targets": ["好友A昵称", "好友B昵称"]
  }
]
```

- `unique_id` 决定 Cookie 变量名：`user1` → 对应 Secret `COOKIES_USER1`（自动转大写）
- `targets` 里填好友的抖音昵称（默认）或抖音号（`MATCH_MODE=short_id` 时）
- 支持多账号：添加多个对象，每个配对应的 `COOKIES_XXX`

### 5. 启用并测试

1. 进入仓库 **Actions** 页面，点击启用 workflow
2. 点左侧 "DouYin Spark AI - 每日续火花" → 右侧 "Run workflow" 手动触发一次
3. 观察运行日志，确认消息发送成功
4. 之后每天北京时间 9:00 自动运行

### 6. 修改运行时间（可选）

编辑 `.github/workflows/schedule.yml` 中的 cron 表达式：

```yaml
cron: "0 1 * * *"  # UTC 时间，北京时间 = UTC + 8
```

常用示例：`30 13 * * *` = 北京 21:30，`0 22 * * *` = 北京次日 6:00。

## AI 配置说明

通过 `AI_PROVIDER` 切换两种 API 格式：

### OpenAI 兼容格式（默认）

`AI_PROVIDER=openai`（或不填）。适用于所有 `/v1/chat/completions` 接口：

| 服务商 | AI_BASE_URL | AI_MODEL |
|--------|-------------|----------|
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-turbo` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| 中转站 | 填中转站给的 base url | 填对应模型名 |
| 本地 Ollama | `http://host.docker.internal:11434/v1` | 自定义 |

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
- 两种都支持的话选 `openai`，兼容性更广

## 本地调试（可选）

```bash
pip install -r requirements.txt
playwright install chromium

export TASKS='[{"username":"我","unique_id":"user1","targets":["好友A"]}]'
export COOKIES_USER1='[...cookie json...]'
export AI_PROVIDER='openai'
export AI_API_KEY='sk-xxx'
export AI_BASE_URL='https://api.deepseek.com'
export AI_MODEL='deepseek-chat'
export HEADLESS='false'  # 可视化浏览器，方便观察
export LOG_LEVEL='DEBUG'

python main.py
```

## FAQ

**Q: API Key 放 GitHub 上安全吗？**

安全。GitHub Secrets 加密存储，运行时才注入环境变量，不出现在日志、代码或任何公开页面。即使仓库 public 别人也看不到。注意别把 key 写进代码 commit 就行。

**Q: 用中转站安全吗？**

取决于中转站可信度。你的聊天上下文会经过中转站服务器。介意隐私就用 DeepSeek / 通义千问官方 API，本身很便宜。

**Q: 每天花多少钱？**

极少。每次约 100-200 token。DeepSeek 价格下 5 个好友跑一个月不到 ¥0.1。Anthropic 贵些但也就几毛。

**Q: Cookie 过期了怎么办？**

Actions 会失败（日志有提示）。重新登录创作者中心 → 导出 Cookie → 更新 GitHub Secret 即可。

**Q: 会被封号吗？**

每天每个好友只发一条消息，和正常使用无异。但任何自动化都有理论风险，建议仅少量好友使用，别批量刷。

**Q: 对方发的视频/图片 AI 能看懂吗？**

目前提取视频卡片上的标题/描述文字给 AI 参考，不是真正"看"视频。没有文字信息时 AI 会发通用问候。

**Q: 支持多账号吗？**

支持。TASKS 里加多个对象，每个配对应 `COOKIES_XXX`。

**Q: 为什么用创作者中心而不是抖音 APP？**

APP 自动化需要 root/越狱，门槛高风险大。创作者中心网页版天然支持私信，Playwright 操作更稳定易部署。

**Q: Actions 突然不跑了？**

GitHub 对 60 天无活动的仓库会禁用 workflow。本项目已内置 keepalive 任务自动保活。如果还是不行，去 Actions 页面手动 re-enable。

## 注意事项

- 抖音网页版存在 A/B 测试，不同账号 DOM 结构不同，代码已做多版本选择器兼容
- 运行失败时先下载 Actions 的 logs artifact 排查
- 本项目仅供学习研究，使用风险自行承担

## License

MIT
