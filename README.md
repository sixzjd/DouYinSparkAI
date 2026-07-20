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

在 GitHub 新建一个空仓库，把本项目代码推上去。

### 2. 获取 Cookie

1. 浏览器打开 https://creator.douyin.com/ 并登录
2. F12 → Application → Cookies，复制全部 Cookie
3. 或者用浏览器插件导出 JSON 格式 Cookie

### 3. 配置环境变量

进入仓库 **Settings → Environments → New environment**，名称填 `user-data`。

在该 Environment 下配置：

**Variables（变量）：**

| 名称 | 说明 | 示例 |
|------|------|------|
| `TASKS` | 任务列表 JSON | 见下方示例 |
| `AI_PROVIDER` | API 格式 | `openai` 或 `anthropic` |
| `AI_BASE_URL` | API 请求地址 | `https://api.deepseek.com` |
| `AI_MODEL` | 模型名称 | `deepseek-chat` |
| `MATCH_MODE` | 好友匹配方式 | `nickname` |

**Secrets（密钥）：**

| 名称 | 说明 |
|------|------|
| `AI_API_KEY` | AI 接口的 API Key |
| `COOKIES_USER1` | 账号1的 Cookie JSON |

### TASKS 格式示例

```json
[
  {
    "username": "我的昵称",
    "unique_id": "user1",
    "targets": ["好友A昵称", "好友B昵称"]
  }
]
```

> `unique_id` 对应 Cookie 环境变量名：`COOKIES_USER1`（自动转大写）

### 4. 启用 Workflow

进入 Actions 页面，点击 "I understand my workflows, go ahead and enable them"。

默认每天北京时间 9:00 自动运行，也可以手动触发测试。

## AI 配置说明

支持两种 API 格式，通过 `AI_PROVIDER` 切换：

### OpenAI 兼容格式（默认）

`AI_PROVIDER` 填 `openai`（或不填，默认就是）。适用于所有提供 `/v1/chat/completions` 接口的服务，包括各种中转站。

| 服务商 | AI_BASE_URL | AI_MODEL |
|--------|-------------|----------|
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-turbo` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| 中转站 | 填中转站给的地址 | 填中转站支持的模型名 |
| 本地 Ollama | `http://host.docker.internal:11434/v1` | 自定义 |

### Anthropic 格式

`AI_PROVIDER` 填 `anthropic`。适用于 Anthropic 官方或支持 Anthropic Messages API 的中转站。

| 场景 | AI_BASE_URL | AI_MODEL |
|------|-------------|----------|
| Anthropic 官方 | 留空（自动用官方地址） | `claude-sonnet-4-20250514` |
| 中转站 | 填中转站地址 | 填对应模型名 |

### 中转站怎么填？

大多数中转站会告诉你"兼容 OpenAI 格式"或"兼容 Anthropic 格式"：

- 兼容 OpenAI → `AI_PROVIDER=openai`，`AI_BASE_URL` 填中转站给的 base url
- 兼容 Anthropic → `AI_PROVIDER=anthropic`，`AI_BASE_URL` 填中转站给的地址
- 如果中转站同时支持两种格式，选哪个都行，OpenAI 格式的兼容性更广

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
export HEADLESS='false'  # 本地调试可视化浏览器
export LOG_LEVEL='DEBUG'

python main.py
```

## FAQ

**Q: API Key 放在 GitHub 上安全吗？**

安全。GitHub Secrets 经过加密存储，运行时注入环境变量，不会出现在日志、代码或任何公开页面中。即使仓库是 public 的，别人也看不到你的 Secret 内容。唯一需要注意的是不要把 key 直接写在代码里或 commit 到仓库。

**Q: 用中转站的 API 安全吗？**

取决于中转站的可信度。你的请求内容（聊天上下文）会经过中转站服务器，所以不要用不可信的中转站。如果介意隐私，建议直接用 DeepSeek / 通义千问等官方 API，价格本身就很便宜。

**Q: 每天调用 AI 要花多少钱？**

极少。每次生成一条回复约 100-200 token。以 DeepSeek 为例（输入 ¥1/百万token，输出 ¥2/百万token），5 个好友每天跑一次，一个月不到 ¥0.1。用 Anthropic Claude 会贵一些但也就几毛钱。

**Q: Cookie 过期了怎么办？**

抖音 Cookie 有效期通常 1-3 个月。过期后 Actions 会运行失败（日志里会提示），重新在浏览器登录创作者中心、导出 Cookie、更新 GitHub Secret 即可。

**Q: 会不会被抖音封号？**

本项目模拟正常人工操作（打开网页、发消息），频率为每天每个好友一条消息，和正常使用无异。但任何自动化操作都有理论风险，建议仅用于少量好友的日常维系，不要批量大量使用。

**Q: 为什么不用抖音 APP 自动操作？**

APP 端自动化需要 root/越狱或无障碍服务，门槛高且风险大。网页版创作者中心天然支持私信功能，用 Playwright 操作更稳定、更易部署。

**Q: 对方发的是视频/图片，AI 能看懂吗？**

目前提取的是视频卡片上显示的标题/描述文字，AI 根据这些文字生成回复。不是真正"看"视频内容。如果卡片没有文字信息，AI 会生成一条通用的自然问候。

**Q: 支持多个账号吗？**

支持。在 TASKS 里添加多个对象，每个对象配对应的 `COOKIES_XXX` 即可。

## 注意事项

- 抖音网页版存在 A/B 测试，不同账号 DOM 结构可能不同，代码已做多版本选择器兼容
- 如果 Actions 运行失败，先查看日志 artifact 定位问题
- 本项目仅供学习研究，使用风险自行承担

## License

MIT
