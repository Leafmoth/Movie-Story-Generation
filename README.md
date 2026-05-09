# Movie Story Generation

一个基于 FastAPI 和 LangGraph 的电影文学剧本生成系统。流水线会按阶段生成并保存：梗概、角色、角色关系、角色小传、三幕式大纲与章节细纲、最终文学剧本。

## 安装

```bash
python -m pip install -r requirements.txt
copy .env.example .env
```

在 `.env` 中填写 `OPENAI_API_KEY`。如果只是测试目录与接口流程，可以设置 `MOCK_LLM=1`。

## 启动 API

```bash
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8001/health
```

生成剧本：

```bash
curl -X POST http://127.0.0.1:8001/generate ^
  -H "Content-Type: application/json" ^
  -d "{\"logline\":\"一个害怕公开发声的女孩发现姐姐的未婚夫是骗子\",\"duration_minutes\":100,\"theme_question\":\"当真相会伤害家人时，还要不要说出来？\",\"genre\":\"家庭悬疑\"}"
```

## 本地 CLI

```bash
python main.py --logline "一个害怕公开发声的女孩发现姐姐的未婚夫是骗子" --duration 100 --theme "当真相会伤害家人时，还要不要说出来？"
```

## 输出

默认输出在 `outputs/project_xxx/`：

- `01_logline.json`
- `02_characters.json`
- `03_relationships.json`
- `04_biography.json`
- `05_outline.json`
- `final_script.md`
