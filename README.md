# Movie Story Generation

一个基于 FastAPI 和 LangGraph 的电影剧本生成系统。流水线会按阶段生成并保存：梗概、角色、角色关系、角色小传、三幕式大纲与章节细纲、文学剧本，以及可选的 XLSX 分镜表格。

## 安装

```bash
python -m pip install -r requirements.txt
copy .env.example .env
```

在 `.env` 中填写 `OPENAI_API_KEY`。如果只是测试目录与接口流程，可以设置 `MOCK_LLM=1`。

## 启动 API

```bash
python -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

## 指令 1：从用户输入直接生成文学剧本和 XLSX 分镜表格

CLI：

```bash
python main.py full --logline "一个害怕公开发声的女孩发现姐姐的未婚夫是骗子" --duration 100 --theme "当真相会伤害家人时，还要不要说出来？" --genre "家庭悬疑"
```

API：

```bash
curl -X POST http://127.0.0.1:8000/generate ^
  -H "Content-Type: application/json" ^
  -d "{\"logline\":\"一个害怕公开发声的女孩发现姐姐的未婚夫是骗子\",\"duration_minutes\":100,\"theme_question\":\"当真相会伤害家人时，还要不要说出来？\",\"genre\":\"家庭悬疑\",\"include_storyboard\":true}"
```

## 指令 2：先只生成文学剧本，再根据文学剧本生成 XLSX 分镜表格

第一步，只生成文学剧本：

```bash
python main.py script --logline "一个害怕公开发声的女孩发现姐姐的未婚夫是骗子" --duration 100 --theme "当真相会伤害家人时，还要不要说出来？" --project-id demo_script
```

第二步，基于已生成的文学剧本继续生成 XLSX 分镜表格：

```bash
python main.py storyboard --project-dir outputs/demo_script
```

也可以直接指定剧本路径：

```bash
python main.py storyboard --script-path outputs/demo_script/final_script.md
```

API 第一步：

```bash
curl -X POST http://127.0.0.1:8000/generate/script-only ^
  -H "Content-Type: application/json" ^
  -d "{\"logline\":\"一个害怕公开发声的女孩发现姐姐的未婚夫是骗子\",\"duration_minutes\":100,\"theme_question\":\"当真相会伤害家人时，还要不要说出来？\",\"project_id\":\"demo_script\"}"
```

API 第二步：

```bash
curl -X POST http://127.0.0.1:8000/storyboard ^
  -H "Content-Type: application/json" ^
  -d "{\"project_id\":\"demo_script\"}"
```

## 输出

默认输出在 `outputs/project_xxx/`：

- `01_logline.json`
- `02_characters.json`
- `03_relationships.json`
- `04_biography.json`
- `05_outline.json`
- `final_script.md`
- `06_storyboard.xlsx`

`06_storyboard.xlsx` 会带横线、竖线分割格子，字体使用低饱和灰色；同一章的分镜连续输出，每一章之间空一行，并保留“时长”和“镜头目的”两列。
