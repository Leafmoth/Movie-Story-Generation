# Movie Story Generation

一个基于 FastAPI、LangGraph 和大模型接口的电影故事生成服务。项目可以根据用户输入的一句话梗概生成：

- 一句话梗概扩展
- 角色设置
- 人物关系
- 人物小传
- 三幕式大纲与章节细纲
- 文学剧本
- 可选的 XLSX 分镜表

当前项目已经封装成 HTTP API，适合通过 ngrok 暴露后接入已有网页前端，作为“大系统”里的一个子功能。

## 快速启动

### 1. 安装依赖

```bash
python -m pip install -r requirements.txt
```

### 2. 配置环境变量

复制示例配置：

```bash
copy .env.example .env
```

常用配置项：

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=
MODEL_NAME=gpt-4o-mini
TEMPERATURE=0.7
REQUEST_TIMEOUT=180
OUTPUT_ROOT=outputs
MOCK_LLM=0

CORS_ALLOW_ORIGINS=*
CORS_ALLOW_CREDENTIALS=0
CORS_ALLOW_METHODS=*
CORS_ALLOW_HEADERS=*
```

说明：

- `DEEPSEEK_API_KEY`：大模型 API Key。
- `DEEPSEEK_BASE_URL`：大模型服务地址；如果使用兼容 OpenAI SDK 的 DeepSeek 接口，在这里填写对应 base url。
- `MODEL_NAME`：模型名称。
- `OUTPUT_ROOT`：生成结果保存目录，默认是 `outputs`。
- `MOCK_LLM=1`：不调用真实模型，只跑通接口流程，适合调试前端。
- `CORS_ALLOW_ORIGINS=*`：允许跨域。正式部署时建议改成你的前端域名，例如 `https://xxx.ngrok-free.app,https://your-site.com`。

### 3. 启动服务

```bash
python -m uvicorn app:app --reload --host 0.0.0.0 --port 9000
```

本地访问：

```text
http://127.0.0.1:9000
```

FastAPI 自动接口文档：

```text
http://127.0.0.1:9000/docs
```

如果使用 ngrok：

```bash
ngrok http 9000
```

前端请求地址示例：

```js
const BASE_URL = "https://你的-ngrok-地址.ngrok-free.app";
```

## 推荐接入方式

推荐前端使用“异步任务接口”：

1. 前端提交故事生成请求。
2. 后端立刻返回 `job_id`。
3. 前端轮询任务状态。
4. 任务完成后，前端分别调用角色、关系、小传、大纲、剧本、分镜等接口展示结果。

这样做的好处是：生成过程较慢时，网页不会一直卡在一个长请求里。

## API 总览

### 健康检查

| 方法 | 路径 | 使用场景 |
|---|---|---|
| `GET` | `/health` | 检查服务是否启动 |

### 推荐给前端使用的异步任务接口

| 方法 | 路径 | 使用场景 |
|---|---|---|
| `POST` | `/api/story-jobs` | 创建故事生成任务 |
| `GET` | `/api/story-jobs/{job_id}` | 查询任务状态 |
| `GET` | `/api/story-jobs/{job_id}/result` | 获取完整生成结果 |
| `GET` | `/api/story-jobs/{job_id}/files/{file_type}` | 下载生成文件 |

### 推荐给前端展示用的过程输出接口

这些接口适合直接显示在网页上。它们都会返回 `display_text` 字段，这是整理后的自然语言/Markdown 文本，建议前端优先展示它。

| 方法 | 路径 | 使用场景 |
|---|---|---|
| `GET` | `/api/story-jobs/{job_id}/characters` | 获取角色设置 |
| `GET` | `/api/story-jobs/{job_id}/relationships` | 获取人物关系 |
| `GET` | `/api/story-jobs/{job_id}/biography` | 获取人物小传 |
| `GET` | `/api/story-jobs/{job_id}/outline` | 获取三幕式大纲与章节细纲 |

### 按历史项目读取过程输出

如果前端或数据库里保存了 `project_id`，可以不用 `job_id`，直接从 `outputs/{project_id}` 读取历史结果。

| 方法 | 路径 | 使用场景 |
|---|---|---|
| `GET` | `/api/projects/{project_id}/characters` | 按项目读取角色设置 |
| `GET` | `/api/projects/{project_id}/relationships` | 按项目读取人物关系 |
| `GET` | `/api/projects/{project_id}/biography` | 按项目读取人物小传 |
| `GET` | `/api/projects/{project_id}/outline` | 按项目读取故事大纲 |

### 旧版同步接口

这些接口仍然保留，适合本地测试或脚本调用。前端正式接入时更推荐使用 `/api/story-jobs`。

| 方法 | 路径 | 使用场景 |
|---|---|---|
| `POST` | `/generate` | 同步生成完整剧本，可包含分镜 |
| `POST` | `/generate/script-only` | 同步生成文学剧本，不生成分镜 |
| `POST` | `/storyboard` | 基于已有文学剧本生成分镜表 |

## 异步任务接口使用方法

### 1. 创建故事生成任务

```http
POST /api/story-jobs
Content-Type: application/json
```

请求体：

```json
{
  "logline": "一个女孩发现姐姐的未婚夫是骗子",
  "duration_minutes": 100,
  "theme_question": "当真相会伤害家人时，还要不要说出来？",
  "genre": "家庭悬疑",
  "include_storyboard": true
}
```

字段说明：

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `logline` | string | 是 | 用户输入的一句话故事梗概 |
| `duration_minutes` | number | 是 | 影片时长，单位分钟 |
| `theme_question` | string | 否 | 主题问题 |
| `genre` | string | 否 | 类型，例如家庭悬疑、爱情、犯罪、科幻 |
| `project_id` | string | 否 | 指定输出项目目录名，不填则自动生成 |
| `include_storyboard` | boolean | 否 | 是否继续生成 XLSX 分镜表，默认 `true` |

响应示例：

```json
{
  "job_id": "52ea5f49feb34670a22845c21fcfb364",
  "status": "pending",
  "status_url": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364",
  "result_url": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364/result"
}
```

前端示例：

```js
const createRes = await fetch(`${BASE_URL}/api/story-jobs`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    logline: "一个女孩发现姐姐的未婚夫是骗子",
    duration_minutes: 100,
    theme_question: "当真相会伤害家人时，还要不要说出来？",
    genre: "家庭悬疑",
    include_storyboard: true
  })
});

const job = await createRes.json();
console.log(job.job_id);
```

### 2. 查询任务状态

```http
GET /api/story-jobs/{job_id}
```

响应示例：

```json
{
  "job_id": "52ea5f49feb34670a22845c21fcfb364",
  "status": "succeeded",
  "created_at": "2026-05-12T00:51:48.000000+00:00",
  "updated_at": "2026-05-12T00:52:30.000000+00:00",
  "project_id": "project_20260512_005148_1fcf235c",
  "error": null,
  "result_url": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364/result",
  "files": {
    "logline": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364/files/logline",
    "characters": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364/files/characters",
    "character_relations": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364/files/character_relations",
    "biography": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364/files/biography",
    "outline": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364/files/outline",
    "final_script": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364/files/final_script",
    "storyboard": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364/files/storyboard"
  }
}
```

`status` 可能的值：

| 状态 | 含义 |
|---|---|
| `pending` | 任务已创建，等待执行 |
| `running` | 正在生成 |
| `succeeded` | 生成成功 |
| `failed` | 生成失败，查看 `error` 字段 |

前端轮询示例：

```js
async function waitStoryJob(jobId) {
  while (true) {
    const res = await fetch(`${BASE_URL}/api/story-jobs/${jobId}`);
    const data = await res.json();

    if (data.status === "succeeded") return data;
    if (data.status === "failed") throw new Error(data.error || "生成失败");

    await new Promise(resolve => setTimeout(resolve, 3000));
  }
}
```

### 3. 获取完整结果

```http
GET /api/story-jobs/{job_id}/result
```

使用场景：

- 前端想一次性拿到全部生成文本。
- 后端想把完整结果保存到自己的数据库。
- 调试时查看所有阶段输出。

响应结构：

```json
{
  "job_id": "52ea5f49feb34670a22845c21fcfb364",
  "status": "succeeded",
  "result": {
    "project_id": "project_20260512_005148_1fcf235c",
    "output_dir": "...",
    "stage_files": {},
    "logline": "...",
    "characters": "...",
    "character_relations": "...",
    "biography": "...",
    "outline": "...",
    "final_script": "...",
    "storyboard": "..."
  },
  "error": null
}
```

注意：这个接口返回的是完整原始结果，可能包含较长文本。网页分模块展示时，建议使用下面的过程输出接口。

## 过程输出接口使用方法

四个过程输出接口都适合给前端页面展示：

```text
GET /api/story-jobs/{job_id}/characters
GET /api/story-jobs/{job_id}/relationships
GET /api/story-jobs/{job_id}/biography
GET /api/story-jobs/{job_id}/outline
```

这些接口的返回体都是 JSON，但其中的 `display_text` 是整理后的自然语言/Markdown 文本，最适合直接展示给用户。

| 字段 | 说明 |
|---|---|
| `job_id` | 当前任务 ID |
| `project_id` | 输出项目 ID |
| `status` | 任务状态 |
| `parsed` | 尽量解析后的 JSON 对象，适合前端做卡片化展示 |
| `display_text` | 给人看的自然语言/Markdown 文本，推荐直接展示 |
| `file_url` | 相关文件或接口地址 |

字段差异：

- `/characters` 返回 `characters`，不返回 `content`。
- `/relationships`、`/biography`、`/outline` 返回 `content`，同时分别返回 `relationships`、`biography`、`outline`。

### 角色设置

```http
GET /api/story-jobs/{job_id}/characters
```

使用场景：

- 在前端显示主角、对手、情感核心人物、盟友、镜像人物。
- 用户生成完成后，先看角色设定是否满意。

前端推荐展示：

```js
const data = await fetch(`${BASE_URL}/api/story-jobs/${jobId}/characters`).then(r => r.json());
document.querySelector("#characters").innerText = data.display_text;
```

响应示例：

```json
{
  "job_id": "52ea5f49feb34670a22845c21fcfb364",
  "project_id": "project_20260512_005148_1fcf235c",
  "status": "succeeded",
  "characters": "...",
  "display_text": "# 角色设置\n\n## 主角\n...",
  "parsed": {},
  "file_url": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364/files/characters"
}
```

### 人物关系

```http
GET /api/story-jobs/{job_id}/relationships
```

使用场景：

- 展示角色之间的冲突、秘密、欲望、关系变化。
- 前端可以把每段关系显示成卡片。

前端推荐展示：

```js
const data = await fetch(`${BASE_URL}/api/story-jobs/${jobId}/relationships`).then(r => r.json());
document.querySelector("#relationships").innerText = data.display_text;
```

响应示例：

```json
{
  "section": "relationships",
  "content": "...",
  "relationships": "...",
  "display_text": "# 人物关系\n\n## 1. 主角和母亲\n...",
  "parsed": {},
  "file_url": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364/files/character_relations"
}
```

### 人物小传

```http
GET /api/story-jobs/{job_id}/biography
```

使用场景：

- 展示主角完整小传、核心配角小传、功能性配角说明。
- 适合给创作者查看人物背景和人物弧光。

前端推荐展示：

```js
const data = await fetch(`${BASE_URL}/api/story-jobs/${jobId}/biography`).then(r => r.json());
document.querySelector("#biography").innerText = data.display_text;
```

### 故事大纲

```http
GET /api/story-jobs/{job_id}/outline
```

使用场景：

- 展示三幕式大纲。
- 展示章节细纲和每个章节的建议时长。
- 适合前端做“故事结构”页面。

前端推荐展示：

```js
const data = await fetch(`${BASE_URL}/api/story-jobs/${jobId}/outline`).then(r => r.json());
document.querySelector("#outline").innerText = data.display_text;
```

## 按 project_id 读取历史结果

如果任务已经完成，响应里会有 `project_id`。生成文件保存在：

```text
outputs/{project_id}/
```

之后即使前端没有 `job_id`，只要有 `project_id`，也可以读取历史阶段结果：

```js
const characters = await fetch(`${BASE_URL}/api/projects/${projectId}/characters`).then(r => r.json());
const relationships = await fetch(`${BASE_URL}/api/projects/${projectId}/relationships`).then(r => r.json());
const biography = await fetch(`${BASE_URL}/api/projects/${projectId}/biography`).then(r => r.json());
const outline = await fetch(`${BASE_URL}/api/projects/${projectId}/outline`).then(r => r.json());
```

这些接口同样提供 `display_text` 字段。

## 文件下载接口

```http
GET /api/story-jobs/{job_id}/files/{file_type}
```

使用场景：

- 下载 `final_script.md` 文学剧本。
- 下载 `06_storyboard.xlsx` 分镜表。
- 下载每个阶段保存的 JSON 文件。

支持的 `file_type`：

| file_type | 对应文件 | 说明 |
|---|---|---|
| `logline` | `01_logline.json` | 一句话梗概扩展 |
| `characters` | `02_characters.json` | 角色设置 |
| `character_relations` | `03_relationships.json` | 人物关系 |
| `relationships` | `03_relationships.json` | `character_relations` 的别名 |
| `biography` | `04_biography.json` | 人物小传 |
| `outline` | `05_outline.json` | 三幕式大纲与章节细纲 |
| `final_script` | `final_script.md` | 文学剧本 |
| `script` | `final_script.md` | `final_script` 的别名 |
| `storyboard` | `06_storyboard.xlsx` | 分镜表 |
| `storyboard_xlsx` | `06_storyboard.xlsx` | `storyboard` 的别名 |

下载示例：

```js
window.open(`${BASE_URL}/api/story-jobs/${jobId}/files/final_script`);
window.open(`${BASE_URL}/api/story-jobs/${jobId}/files/storyboard`);
```

## 旧版同步接口

### 同步生成完整结果

```http
POST /generate
Content-Type: application/json
```

请求体：

```json
{
  "logline": "一个女孩发现姐姐的未婚夫是骗子",
  "duration_minutes": 100,
  "theme_question": "当真相会伤害家人时，还要不要说出来？",
  "genre": "家庭悬疑",
  "include_storyboard": true
}
```

使用场景：

- 本地测试。
- 后端脚本调用。
- 不需要轮询任务状态的小规模场景。

不建议直接给网页前端使用，因为生成过程可能较慢，容易造成请求超时。

### 只生成文学剧本

```http
POST /generate/script-only
Content-Type: application/json
```

请求体同 `/generate`。

使用场景：

- 只需要文学剧本。
- 暂时不需要 XLSX 分镜表。

### 基于已有剧本生成分镜表

```http
POST /storyboard
Content-Type: application/json
```

请求体三选一：

```json
{
  "project_id": "project_20260512_005148_1fcf235c"
}
```

或：

```json
{
  "script_path": "outputs/project_20260512_005148_1fcf235c/final_script.md"
}
```

或：

```json
{
  "final_script": "这里传入完整文学剧本文本",
  "project_id": "manual_storyboard"
}
```

使用场景：

- 已经有文学剧本，只想补生成分镜表。
- 前端拆成“先生成剧本，再生成分镜”两步。

## CLI 使用方法

项目也保留了命令行入口 [main.py](main.py)。

### 生成完整剧本和分镜

```bash
python main.py full --logline "一个女孩发现姐姐的未婚夫是骗子" --duration 100 --theme "当真相会伤害家人时，还要不要说出来？" --genre "家庭悬疑"
```

### 只生成文学剧本

```bash
python main.py script --logline "一个女孩发现姐姐的未婚夫是骗子" --duration 100 --theme "当真相会伤害家人时，还要不要说出来？" --project-id demo_script
```

### 基于已有剧本生成分镜

```bash
python main.py storyboard --project-dir outputs/demo_script
```

或：

```bash
python main.py storyboard --script-path outputs/demo_script/final_script.md
```

## 输出目录

每次生成会在 `outputs` 下创建一个项目目录：

```text
outputs/
  project_20260512_005148_1fcf235c/
    01_logline.json
    02_characters.json
    03_relationships.json
    04_biography.json
    05_outline.json
    final_script.md
    06_storyboard.xlsx
```

文件说明：

| 文件 | 内容 |
|---|---|
| `01_logline.json` | 一句话梗概扩展 |
| `02_characters.json` | 角色设置 |
| `03_relationships.json` | 人物关系 |
| `04_biography.json` | 人物小传 |
| `05_outline.json` | 三幕式大纲与章节细纲 |
| `final_script.md` | 文学剧本 |
| `06_storyboard.xlsx` | 分镜表，当前使用 10 列镜头生成格式，最后一列“修改建议落地”默认留空 |

## 项目目录结构

```text
MoiveStoryGeneration/
  app.py                    # FastAPI 服务入口，包含所有 HTTP 接口
  main.py                   # 命令行入口
  requirements.txt          # Python 依赖
  README.md                 # 项目说明文档
  .env.example              # 环境变量示例

  config/
    settings.py             # 环境变量读取、模型配置、CORS 配置、输出目录配置

  core/
    orchestrator.py         # 生成流程编排，串联各个生成阶段
    llm_client.py           # 大模型调用封装，支持 MOCK_LLM
    stage_base.py           # 通用 PromptStage 基类
    storage.py              # 输出文件保存、JSON 提取工具
    state.py                # LangGraph 状态结构定义

  stages/
    logline_stage.py        # 一句话梗概扩展阶段
    character_stage.py      # 角色设置阶段
    relationship_stage.py   # 人物关系阶段
    biography_stage.py      # 人物小传阶段
    outline_stage.py        # 三幕式大纲与章节细纲阶段
    scene_write_stage.py    # 文学剧本阶段
    storyboard_stage.py     # XLSX 分镜表阶段
    act_detail_stage.py     # 预留/扩展阶段
    scene_plan_stage.py     # 预留/扩展阶段
    polish_stage.py         # 预留/扩展阶段

  prompts/
    logline_prompt.txt      # 梗概扩展提示词
    character_prompt.txt    # 角色设置提示词
    relationship_prompt.txt # 人物关系提示词
    biography_prompt.txt    # 人物小传提示词
    outline_prompt.txt      # 大纲提示词
    scene_write_prompt.txt  # 文学剧本提示词
    storyboard_prompt.txt   # 旧版分镜表提示词，保留备用
    storyboard_prompt2.txt  # 当前主业务使用的新版镜头生成提示词

  schemas/
    story.py                # API 请求/响应模型
    character.py            # 角色相关模型，预留扩展
    outline.py              # 大纲相关模型，预留扩展
    scene.py                # 场景相关模型，预留扩展

  outputs/
    project_xxx/            # 每次生成的结果文件
```

## 功能流程说明

完整生成流程由 [core/orchestrator.py](core/orchestrator.py) 编排。

```text
用户输入
  |
  v
logline 一句话梗概扩展
  |
  v
characters 角色设置
  |
  v
relationships 人物关系
  |
  v
biography 人物小传
  |
  v
outline 三幕式大纲与章节细纲
  |
  v
scene_write 文学剧本
  |
  v
storyboard 分镜表，可选
```

每个阶段都会：

1. 读取 `prompts/` 下对应提示词。
2. 把前面阶段的结果填入提示词模板。
3. 调用大模型生成内容。
4. 保存到 `outputs/{project_id}/`。
5. 把结果写回任务状态，供 API 查询。

当前分镜阶段使用 `prompts/storyboard_prompt2.txt`，生成 `06_storyboard.xlsx` 时会按以下列输出：

```text
# | 场次-镜号 | 画面核心内容 | 光学参数 | 景别 | 运镜调度 | 构图要求（前+中+后） | 光影色彩 风格 | 物理/AI 约束 | 修改建议落地
```

其中最后一列“修改建议落地”会在写入 Excel 时强制留空。

## 前端展示建议

前端展示过程输出时，优先使用：

```js
data.display_text
```

不要直接展示：

```js
data.content
data.parsed
```

原因：

- `content` 是原始模型输出，可能是 JSON 字符串。
- `parsed` 适合程序处理，不适合直接给用户看。
- `display_text` 已经整理成自然语言/Markdown，更适合人阅读。

简单展示：

```jsx
<pre style={{ whiteSpace: "pre-wrap" }}>
  {data.display_text}
</pre>
```

如果你的前端支持 Markdown，可以用 Markdown 渲染器显示，效果会更好。

## 当前实现注意事项

- 异步任务状态目前保存在进程内存中，服务重启后 `job_id` 状态会丢失。
- 生成结果文件会保存到 `outputs/{project_id}`，所以即使服务重启，只要知道 `project_id`，仍然可以通过 `/api/projects/{project_id}/...` 读取历史阶段结果。
- 当前后台任务使用 `ThreadPoolExecutor(max_workers=2)`，默认最多同时执行 2 个生成任务。
- 如果要生产部署、多进程部署或多机器部署，建议把任务状态迁移到 Redis 或数据库。
- 如果通过 ngrok 暴露给前端，确保 `.env` 里的 `CORS_ALLOW_ORIGINS` 包含你的前端域名，或开发阶段使用 `*`。
