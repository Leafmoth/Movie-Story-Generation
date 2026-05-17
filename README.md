# Movie Story Generation

一个基于 FastAPI、LangGraph 和大模型接口的电影故事生成服务。项目可以根据用户输入的一句话梗概生成：

- 一句话梗概扩展
- 角色设置
- 人物关系
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

当前 `/api/story-jobs` 统一使用新版“阶段生成 + 自选人工确认”流程。前端通过 `confirm_stages` 决定哪些阶段需要用户确认；没有选中的阶段会自动继续。旧同步接口 `/generate`、`/generate/script-only` 仍保留用于本地测试或兼容，不建议前端主流程调用。

## API 总览

### 健康检查

| 方法 | 路径 | 使用场景 |
|---|---|---|
| `GET` | `/health` | 检查服务是否启动 |

### 推荐给前端使用的异步任务接口

| 方法 | 路径 | 使用场景 |
|---|---|---|
| `POST` | `/api/story-jobs` | 创建故事生成任务 |
| `GET` | `/api/story-generation-options` | 获取前端可配置项，例如角色字段和评论家默认重试次数 |
| `GET` | `/api/story-jobs/{job_id}` | 查询任务状态 |
| `GET` | `/api/story-jobs/{job_id}/stream` | 通过 SSE 流式接收任务状态和阶段内容 |
| `GET` | `/api/story-jobs/{job_id}/result` | 获取完整生成结果 |
| `GET` | `/api/story-jobs/{job_id}/files/{file_type}` | 下载生成文件 |
| `GET` | `/api/story-jobs/{job_id}/stages/{stage}` | 读取交互式流程的某个阶段输出 |
| `PATCH` | `/api/story-jobs/{job_id}/stages/{stage}` | 保存前端编辑后的阶段内容 |
| `POST` | `/api/story-jobs/{job_id}/confirm` | 确认或反馈修改当前等待确认的阶段 |
| `POST` | `/api/story-jobs/{job_id}/interrupt-regenerate` | 打断当前任务并创建一个重新生成的新任务 |
| `POST` | `/api/story-jobs/{job_id}/restart-from-stage` | 从指定阶段重新开始生成当前任务 |

### 推荐给前端展示用的过程输出接口

这些接口适合直接显示在网页上。它们都会返回 `display_text` 字段，这是整理后的自然语言/Markdown 文本，建议前端优先展示它。

| 方法 | 路径 | 使用场景 |
|---|---|---|
| `GET` | `/api/story-jobs/{job_id}/characters` | 获取角色设置 |
| `GET` | `/api/story-jobs/{job_id}/relationships` | 获取人物关系 |
| `GET` | `/api/story-jobs/{job_id}/relationship-graph` | 获取前端关系图 JSON |
| `GET` | `/api/story-jobs/{job_id}/biography` | 旧字段读取；新版任务不再生成，建议使用角色设置和人物关系 |
| `GET` | `/api/story-jobs/{job_id}/outline` | 获取三幕式大纲与章节细纲 |

### 按历史项目读取过程输出

如果前端或数据库里保存了 `project_id`，可以不用 `job_id`，直接从 `outputs/{project_id}` 读取历史结果。

| 方法 | 路径 | 使用场景 |
|---|---|---|
| `GET` | `/api/projects/{project_id}/characters` | 按项目读取角色设置 |
| `GET` | `/api/projects/{project_id}/relationships` | 按项目读取人物关系 |
| `GET` | `/api/projects/{project_id}/relationship-graph` | 按项目读取前端关系图 JSON |
| `GET` | `/api/projects/{project_id}/biography` | 按历史项目读取旧版人物小传 |
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
| `pass_score` | number | 否 | 评论家通过分数，默认 `85`，预留给评论家迭代流程 |
| `character_detail_fields` | string[] | 否 | 前端勾选的可选角色字段，例如 `["职业","人物弧光"]` |
| `max_critic_retries` | number | 否 | 大纲评论家未通过时最多自动重试次数，默认 `3` |
| `workflow_mode` | string | 否 | `auto` 或 `interactive`，默认 `auto` |
| `confirm_stages` | string[] | 否 | 确认节点，默认 `["logline","world","characters","relationships","outline","final_script"]`；传 `[]` 表示全程不干预 |

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
    "world": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364/files/world",
    "characters": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364/files/characters",
    "character_relations": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364/files/character_relations",
    "relationship_graph": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364/files/relationship_graph",
    "outline": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364/files/outline",
    "outline_critic": "/api/story-jobs/52ea5f49feb34670a22845c21fcfb364/files/outline_critic",
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
| `waiting_confirmation` | 交互式流程正在等待用户确认或反馈 |
| `cancelled` | 已被前端打断；如通过重新生成接口触发，查看 `replaced_by_job_id` |

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

### 2.1 流式接收任务进度

如果前端不想轮询，可以用 SSE：

```http
GET /api/story-jobs/{job_id}/stream
```

前端示例：

```js
const source = new EventSource(`${BASE_URL}/api/story-jobs/${jobId}/stream`);

source.addEventListener("job", event => {
  const data = JSON.parse(event.data);
  const job = data.job;

  // 状态、当前阶段、可用阶段、评论家报告
  console.log(job.status, job.current_stage, job.available_sections);

  // 当前阶段内容快照
  if (data.current_stage_output) {
    renderStage(data.current_stage_output.section, data.current_stage_output.display_text);
  }

  // 已可用阶段的结构化数据，例如 characters / relationship_graph / outline_critic
  if (data.available_outputs?.relationship_graph) {
    renderGraph(data.available_outputs.relationship_graph.parsed.relationship_graph);
  }
});

source.addEventListener("done", event => {
  const data = JSON.parse(event.data);
  console.log("job finished", data.status);
  source.close();
});

source.addEventListener("error", () => {
  source.close();
});
```

这个流式接口会同时推送“任务状态快照”和“模型 token 增量”。现有轮询接口仍然保留。

现在 SSE 同时支持模型 token 级输出。前端监听 `token` 事件即可拿到模型实时增量：

```js
const source = new EventSource(`${BASE_URL}/api/story-jobs/${jobId}/stream`);

source.addEventListener("token", event => {
  const data = JSON.parse(event.data);

  // data.stage: logline / world / characters / outline / final_script / storyboard
  // data.model_stage: 更细的内部阶段，例如 scene_write_chunk
  // data.token: 本次模型增量
  // data.meta: 剧本片段或分镜批次信息
  appendToken(data.stage, data.token, data.meta);
});

source.addEventListener("job", event => {
  const data = JSON.parse(event.data);
  renderSnapshot(data);
});
```

`token` 事件是真正来自模型 `stream=True` 的 delta；`job` 事件仍是后端状态快照，用于阶段、进度、可用内容和完成状态展示。

文学剧本阶段会在每个剧本片段完成后更新一次任务快照。SSE 的 `job` 事件在 `current_stage === "final_script"` 时会额外包含：

```json
{
  "script_segment_progress": {
    "completed": 2,
    "total": 8,
    "done": false
  },
  "script_segments": [
    {
      "title": "第一章",
      "script_text": "...",
      "continuity_notes": "..."
    }
  ],
  "current_stage_output": {
    "section": "final_script",
    "content": "已经合并好的当前剧本片段..."
  }
}
```

如果前端 SSE 仍不稳定，可以轮询剧本片段接口：

```http
GET /api/story-jobs/{job_id}/stages/final_script/segments
```

这个接口会返回当前已完成的 `segments`、合并后的 `content` 和 `progress`，适合前端在剧本阶段每 500ms-1000ms 拉取一次。

### 交互式确认流程

创建任务时传入：

```json
{
  "logline": "一个女孩发现姐姐的未婚夫是骗子",
  "duration_minutes": 100,
  "theme_question": "当真相会伤害家人时，还要不要说出来？",
  "genre": "家庭悬疑",
  "include_storyboard": true,
  "workflow_mode": "interactive"
}
```

当任务状态为 `waiting_confirmation` 时，状态接口会返回：

```json
{
  "status": "waiting_confirmation",
  "current_stage": "world",
  "pending_confirmation": {
    "stage": "world",
    "stage_url": "/api/story-jobs/{job_id}/stages/world",
    "actions": ["approve", "revise"]
  },
  "confirmed_stages": ["logline"],
  "revision_counts": {},
  "available_sections": ["logline", "world"]
}
```

读取阶段内容：

```http
GET /api/story-jobs/{job_id}/stages/{stage}
```

支持的 `stage`：

```text
logline
world
characters
relationships
relationship_graph
outline
outline_critic
final_script
storyboard
```

`confirm_stages` 就是前端的干预选择项：选中的模块会暂停等待用户确认；没选中的模块等同于用户一直选择通过，会自动继续；如果传空数组 `[]`，则全流程不让用户参与，只在最后返回剧本和分镜。如果前端希望“每生成完一个节点都可查看和编辑”，建议传 `["logline","world","characters","relationships","relationship_graph","outline","final_script","storyboard"]`。

保存用户在输入框里编辑后的阶段内容：

```http
PATCH /api/story-jobs/{job_id}/stages/{stage}
Content-Type: application/json
```

```json
{
  "content": "前端输入框里的完整新内容",
  "invalidate_downstream": true,
  "note": "用户手动调整了人物动机"
}
```

说明：

- `content` 会写回该阶段状态和对应输出文件。
- `invalidate_downstream` 默认为 `true`，会清理该阶段之后已经生成的旧结果，避免上游修改后下游仍使用旧内容。
- 任务正在 `running` 时不能直接编辑，前端应通过 `confirm_stages` 让任务停在该阶段后再保存。
- 保存后如果用户满意，再调用 `/confirm` 的 `approve` 继续；如果希望模型按反馈重跑当前阶段，则调用 `/confirm` 的 `revise`。

新版 `/api/story-jobs` 不再生成人物小传 `biography`。人物信息由 `characters` 角色设置和 `relationships` 人物关系共同提供给大纲与剧本阶段。

角色设置默认生成这些字段：姓名、身高、体重、年龄、外貌、感情生活、道德标准、情商智商、人物创伤、人物缺陷、人物性格、人物选择、人物动机。其余社会维度和内部字段由前端通过 `character_detail_fields` 勾选追加。

大纲生成后会自动调用评论家检查世界观、角色逻辑、因果、时间线和时长预算。后端会校验大纲章节总时长是否匹配 `duration_minutes`，三幕比例是否接近 25% / 50% / 25%。如果评论家或时长检查未通过，会把 `revision_advice` 反馈给大纲阶段重写，最多重试 `max_critic_retries` 次。重试耗尽仍未通过时，任务会停在 `outline` 的人工确认点，状态里的 `critic_reports` 会给出每次评分和修改建议。

文学剧本会继承大纲的章节时长预算，分镜表生成后会汇总“时长”列。若分镜总时长偏离目标超过 `max(1分钟, 目标时长的5%)`，后端会自动带反馈重跑分镜；这些检查不需要前端新增接口或改请求结构。

为降低模型长输出被截断的风险，后端不会一次性生成完整文学剧本或完整分镜：

- 文学剧本阶段会按 `chapter_outline` 逐章节生成小片段，每次只要求模型输出一个 JSON 对象；片段会经过内部评论家检查，通过后再由后端合并成原来的 `final_script.md`。
- 每个剧本片段会带入全局世界观、角色设置、人物关系和最近 3 个已完成片段的连续性摘要，避免分段生成割裂。
- 分镜阶段会把最终剧本拆成小批次，每批约 600 字以内、最多 3 句真实对白、最多 6 个镜头，模型只输出当前批次 JSON 数组。
- 后端会解析 JSON、校验对白覆盖、重写镜号、合并为原来的 CSV/XLSX；批次失败会先重试，再继续拆小，仍失败则明确报错，不静默跳过。

确认通过并继续：

```http
POST /api/story-jobs/{job_id}/confirm
Content-Type: application/json
```

```json
{
  "stage": "world",
  "action": "approve"
}
```

要求根据用户反馈重跑当前阶段：

```json
{
  "stage": "world",
  "action": "revise",
  "feedback": "世界观更偏现实主义，减少类型化巧合。"
}
```

如果用户否认的是 `logline` 阶段，需要额外传 `revision_mode`：

```json
{
  "stage": "logline",
  "action": "revise",
  "revision_mode": "modify",
  "feedback": "保留姐姐婚礼，但让主角动机更私人。"
}
```

`revision_mode: "modify"` 表示基于上一版故事梗概和用户反馈修改；`revision_mode: "rewrite"` 表示直接用用户新输入的故事重写本阶段。

交互式流程会新增 `02_world.json`、`workflow_state.json`、`revision_history.json`。其中 `world` 也可以通过历史项目接口读取：

```http
GET /api/projects/{project_id}/world
```

### 打断并重新生成

前端用户点击“重新生成”时，调用：

```http
POST /api/story-jobs/{job_id}/interrupt-regenerate
Content-Type: application/json
```

请求体可以为空，表示复用旧任务参数；也可以传入覆盖字段：

### 从指定阶段重新开始

如果用户在后续阶段发现上游内容不满意，比如任务已经到 `outline`，但用户想回到 `world` 从世界观开始重新生成，调用：

```http
POST /api/story-jobs/{job_id}/restart-from-stage
Content-Type: application/json
```

```json
{
  "stage": "world",
  "feedback": "世界观改成更现实主义，减少奇幻设定",
  "revision_mode": "modify"
}
```

后端会清理 `world` 及其下游旧结果，然后从 `world` 重新跑。上游阶段，比如 `logline`，会保留。  
当前任务正在 `running` 时不能直接回退，前端应等任务进入 `waiting_confirmation`、`succeeded` 或 `failed` 后再调用；如果必须中断正在运行的任务，先用 `/interrupt-regenerate` 创建新任务。

```json
{
  "logline": "用户重新输入的一句话梗概",
  "character_detail_fields": ["职业", "人物弧光"],
  "max_critic_retries": 3
}
```

接口会立即把旧任务标记为 `cancelled`，并返回新任务的 `job_id`。旧任务状态中会记录 `replaced_by_job_id`。

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
    "biography": "",
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
- `/relationships`、`/outline` 返回 `content`，同时分别返回 `relationships`、`outline`。

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

### 人物信息

新版 `/api/story-jobs` 不再单独生成人物小传。前端应展示：

```http
GET /api/story-jobs/{job_id}/characters
GET /api/story-jobs/{job_id}/relationships
```

这两部分共同作为后续故事大纲和文学剧本的人物依据。

### 故事大纲

```http
GET /api/story-jobs/{job_id}/outline
```

使用场景：

- 展示三幕式大纲。
- 展示章节细纲和每个章节的数字时长预算。
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
const relationshipGraph = await fetch(`${BASE_URL}/api/projects/${projectId}/relationship-graph`).then(r => r.json());
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
| `world` | `02_world.json` | 世界观设定 |
| `characters` | `02_characters.json` | 角色设置 |
| `character_relations` | `03_relationships.json` | 人物关系 |
| `relationships` | `03_relationships.json` | `character_relations` 的别名 |
| `relationship_graph` | `03_relationship_graph.json` | 前端关系图 JSON |
| `biography` | `04_biography.json` | 旧版人物小传；新版任务不再生成 |
| `outline` | `05_outline.json` | 三幕式大纲与章节细纲 |
| `outline_critic` | `05_outline_critic.json` | 大纲评论家报告 |
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
    02_world.json
    02_characters.json
    03_relationships.json
    03_relationship_graph.json
    05_outline.json
    05_outline_critic.json
    final_script.md
    06_storyboard.xlsx
```

文件说明：

| 文件 | 内容 |
|---|---|
| `01_logline.json` | 一句话梗概扩展 |
| `02_world.json` | 世界观设定 |
| `02_characters.json` | 角色设置 |
| `03_relationships.json` | 人物关系 |
| `03_relationship_graph.json` | 前端关系图 JSON |
| `05_outline.json` | 三幕式大纲与章节细纲 |
| `05_outline_critic.json` | 大纲评论家报告 |
| `final_script.md` | 文学剧本 |
| `06_storyboard.xlsx` | 分镜表 |

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
    world_stage.py          # 世界观设定阶段
    character_stage.py      # 角色设置阶段
    relationship_stage.py   # 人物关系阶段
    relationship_graph_stage.py # 前端关系图阶段
    critic_stage.py         # 评论家评价阶段
    outline_stage.py        # 三幕式大纲与章节细纲阶段
    scene_write_stage.py    # 文学剧本阶段
    storyboard_stage.py     # XLSX 分镜表阶段
    act_detail_stage.py     # 预留/扩展阶段
    scene_plan_stage.py     # 预留/扩展阶段
    polish_stage.py         # 预留/扩展阶段

  prompts/
    logline_prompt.txt      # 梗概扩展提示词
    world_prompt.txt        # 世界观提示词
    character_prompt.txt    # 角色设置提示词
    relationship_prompt.txt # 人物关系提示词
    relationship_graph_prompt.txt # 前端关系图提示词
    critic_prompt.txt       # 评论家提示词
    outline_prompt.txt      # 大纲提示词
    scene_write_prompt.txt  # 文学剧本提示词
    storyboard_prompt.txt   # 分镜表提示词

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
world 世界观设定
  |
  v
characters 角色设置
  |
  v
relationships 人物关系
  |
  v
relationship_graph 前端关系图
  |
  v
outline 三幕式大纲、章节细纲与时长预算
  |
  v
outline_critic 评论家与时长检查，不通过则按建议重试大纲
  |
  v
scene_write 文学剧本，继承章节时长预算
  |
  v
storyboard 分镜表，可选；生成后校验总时长
```

每个阶段都会：

1. 读取 `prompts/` 下对应提示词。
2. 把前面阶段的结果填入提示词模板。
3. 调用大模型生成内容。
4. 保存到 `outputs/{project_id}/`。
5. 把结果写回任务状态，供 API 查询。

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
