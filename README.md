# DouYinSparkAI

抖音智能续火花 —— 自动检测好友消息，AI 生成个性化回复，火花永不断。

## 工作原理

1. 通过 Playwright 无头浏览器登录抖音创作者中心网页版
2. 打开与目标好友的聊天窗口，读取最近消息
3. 如果今天已经发过消息 → 跳过（不重复发）
4. 如果对方发了视频 → 提取视频标题/描述作为上下文
5. 调用 AI（DeepSeek 等）根据上下文生成自然回复
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
| `AI_BASE_URL` | AI 接口地址 | `https://api.deepseek.com` |
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

使用 OpenAI 兼容格式，支持任何兼容接口：

| 服务商 | AI_BASE_URL | AI_MODEL |
|--------|-------------|----------|
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-turbo` |
| 本地 Ollama | `http://host.docker.internal:11434/v1` | 自定义 |

每次调用消耗约 100-200 token，DeepSeek 价格下每月几毛钱。

## 本地调试（可选）

```bash
pip install -r requirements.txt
playwright install chromium

export TASKS='[{"username":"我","unique_id":"user1","targets":["好友A"]}]'
export COOKIES_USER1='[...cookie json...]'
export AI_API_KEY='sk-xxx'
export AI_BASE_URL='https://api.deepseek.com'
export AI_MODEL='deepseek-chat'
export HEADLESS='false'  # 本地调试可视化浏览器
export LOG_LEVEL='DEBUG'

python main.py
```

## 注意事项

- Cookie 有效期通常 1-3 个月，过期后需重新获取
- 抖音网页版存在 A/B 测试，不同账号 DOM 结构可能不同，代码已做多版本兼容
- 建议仅用于个人少量好友的火花维系，频率不要过高
- 本项目仅供学习研究，使用风险自行承担

## License

MIT
