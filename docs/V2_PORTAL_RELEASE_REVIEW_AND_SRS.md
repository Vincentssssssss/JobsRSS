# JobsRSS V2 Portal 发版评审文档（结构梳理 + 集中测试 + 简版SRS）

## 1. 文档目标

本文件用于 V2 发版前评审，覆盖：

1. 当前 Portal 页面设计结构与逻辑结构  
2. 系统模块、技术栈、依赖工具与关键配置  
3. 集中测试方案（可执行）  
4. 简版软件需求说明书（SRS）供 review

配套架构图见：`docs/V2_ARCHITECTURE_DIAGRAM.md`

---

## 2. 当前系统边界与总体结构

```text
[User Browser]
   -> Frontend (Next.js 16, React 19)
      -> API calls (/jobs, /jobs/count, /jobs/summary/last-24h, /sources/official, /jobs/{id})
         -> Backend API (FastAPI)
            -> PostgreSQL

[Worker APScheduler]
   -> LinkedIn/Liepin/51job collectors
   -> Official source collectors (V2)
   -> LLM rerank job
   -> Daily digest job
```

### 2.1 服务拓扑（Docker Compose）

- `postgres`: 数据库
- `api`: FastAPI（端口 8000）
- `worker`: APScheduler 定时采集与重排
- `frontend`: Next.js portal（端口 3000）

---

## 3. 页面设计结构（基于当前 `frontend/app/page.tsx`）

Portal 为单页结构，核心区块如下：

1. **Hero 区**
   - 标题：JobsRSS Intelligence
   - 两个快捷入口：`High Match RSS`、`All Jobs RSS`

2. **Stats 区**
   - `Total Loaded`
   - `High Match (80+)`
   - `Last 24h New`
   - `Last 24h High Match`

3. **Filters 区**
   - Search（关键词）
   - Source（数据源）
   - AI Precision Mode（On/Off）
   - Rule Score
   - Fetch Limit
   - AI Score
   - Location Classification

4. **Source Summary 区**
   - 24小时来源分布 chips（可选显示）

5. **Job List 区**
   - 卡片字段：company/title/location/source/post time/score
   - 行为：Apply Now、View Details
   - 空态：提示当前筛选无结果，而非直接暗示采集异常

6. **Job Detail Overlay**
   - 详情弹层
   - 分段描述（description sections）
   - LLM match/reject reasons

---

## 4. 页面逻辑结构（关键行为）

## 4.1 数据加载策略

- 初始与筛选变化时并行触发：
  - `loadJobs()`
  - `loadSummary()`
  - `loadCount()`
- 独立触发：
  - `loadOfficialSources()`
  - `loadJobDetail(jobId)`

## 4.2 API请求与容错

前端使用 `fetchJsonWithFallback`，按候选地址顺序请求：

1. `http(s)://<当前浏览器host>:8000`
2. `http://localhost:8000`
3. `http://127.0.0.1:8000`
4. `/api/backend`（代理备用）

任一路径成功返回 JSON 即使用；失败则尝试下一路径。

## 4.3 筛选参数映射

- 基础参数：
  - `limit`
  - `min_score`
  - `q`
  - `source`
  - `location_category`

- AI Precision Mode = **On**
  - 强制 `llm_verdict=strong_fit,possible_fit`
  - 若设置 AI Score，则追加 `min_llm_score`

- AI Precision Mode = **Off**
  - `min_score` 使用 Rule Score
  - 可选 `min_llm_score`

## 4.4 分数显示优先级

- 若存在 `llm_fit_score`：显示 `AI xx`
- 否则显示 `Rule xx`

---

## 5. 后端逻辑与数据更新机制

## 5.1 API端点（Portal依赖）

- `GET /jobs`
- `GET /jobs/count`
- `GET /jobs/summary/last-24h`
- `GET /jobs/{id}`
- `GET /sources/official`
- `GET /rss/all.xml`
- `GET /rss/high-match.xml`
- `GET /healthz`

## 5.2 调度与实时性定义

系统为**轮询更新**，非流式实时：

- LinkedIn/Liepin/51job：按各自 `*_polling_interval_minutes`
- Official sources：`OFFICIAL_SOURCE_INTERVAL_MINUTES`
- LLM重排：`LLM_RERANK_INTERVAL_MINUTES`

因此“实时”在本系统定义为：**分钟级周期更新**。

## 5.3 LLM重排关键策略

- 只对 `active` 且满足规则分数下限的职位重排
- 支持 `LLM_ONLY_UNSCORED`
- 增加早期职业岗位硬拦截（校招/应届/实习等）避免误判

---

## 6. 技术栈、组件模块、工具与配置

## 6.1 技术栈

- Frontend: Next.js 16, React 19, TypeScript
- Backend: FastAPI, SQLAlchemy, Pydantic Settings
- Worker: APScheduler
- DB: PostgreSQL 16
- Container: Docker Compose
- 抓取：Playwright + source-specific parsers
- LLM API: OpenAI-compatible (OpenAI / ChatGPT / Codex / Qwen / Azure-compatible)

## 6.2 关键模块

- `frontend/app/page.tsx`：主页面与交互逻辑
- `frontend/app/api/backend/[...path]/route.ts`：代理转发（备用路径）
- `backend/app/api/routes/jobs.py`：列表/计数/汇总/详情
- `backend/app/api/routes/sources.py`：官方源状态
- `backend/app/scheduler/runner.py`：采集与LLM调度入口
- `backend/app/matching/llm_reranker.py`：LLM重排与硬规则护栏
- `backend/app/core/config.py`：统一配置

## 6.3 关键配置（建议重点检查）

### 网络与跨源

- `ALLOWED_ORIGINS`（支持 JSON 数组或逗号分隔）
- 前端访问建议：`localhost:3000` 与 `127.0.0.1:3000` 均验证

### 采集与轮询

- `OFFICIAL_SOURCES_ENABLED`
- `OFFICIAL_SOURCE_INTERVAL_MINUTES`
- `LINKEDIN_AUTH_ENABLED`
- `LIEPIN_AUTH_ENABLED`
- `*_AUTH_STORAGE_STATE_PATH`

### LLM重排

- `LLM_RERANK_ENABLED`
- `LLM_PROVIDER`
- `LLM_MODEL`
- `LLM_RERANK_INTERVAL_MINUTES`
- `LLM_MAX_JOBS_PER_RUN`
- `LLM_MIN_RULE_SCORE`
- `LLM_ONLY_UNSCORED`
- `LLM_REJECT_EARLY_CAREER`
- `LLM_TARGET_PROFILE`

---

## 7. V2 集中测试方案（发布前）

## 7.1 测试目标

- 确认页面“可见性、正确性、稳定性”
- 确认采集链路与LLM链路持续更新
- 确认筛选逻辑与数字一致性

## 7.2 测试用例（建议最小集合）

1. **API基础连通**
   - `GET /healthz` 返回 200 + version
   - `GET /jobs/count?status=active&min_score=0` 返回数字

2. **页面总数一致性**
   - Portal `Total Loaded` 应与 `jobs/count` 同条件一致

3. **AI Precision 模式**
   - On + `AI Score=60`：应等于 `llm_verdict=strong_fit,possible_fit&min_llm_score=60`
   - On + `AI Score=All`：不应隐式带 `min_llm_score=60`

4. **Off 模式规则筛选**
   - Rule Score=0/60/80 对应结果递减

5. **详情弹层**
   - `View Details` 成功加载
   - `description_sections` 可渲染

6. **RSS可读性**
   - `all.xml`、`high-match.xml` 非乱码
   - 中文可读

7. **数据源状态**
   - `GET /sources/official` 返回 first_wave 与 operational 字段

8. **更新性验证**
   - 观察 worker 日志中的 `collector_run` 与 `llm_rerank_run`
   - 验证 `found/new/duplicates/errors` 指标变化

## 7.3 发布门槛（Go/No-Go）

- API健康检查连续稳定
- 页面总数与 API 一致
- 关键筛选逻辑无明显偏差
- RSS 非乱码
- 至少一轮采集 + 一轮LLM重排成功

---

## 8. 简版软件需求说明书（SRS）

## 8.1 产品目标

面向网络安全职业画像，聚合多源岗位，按规则与AI双重筛选，并通过 Portal/RSS 提供可申请岗位。

## 8.2 用户角色

- 主要用户：求职者（安全岗位）
- 运维用户：系统维护/调参人员

## 8.3 功能需求（FR）

- FR-01 多源采集：支持 LinkedIn/Liepin/官方站点等
- FR-02 统一建模：职位统一字段结构入库
- FR-03 去重更新：避免重复，保留新鲜度
- FR-04 规则打分：计算 `match_score`
- FR-05 LLM重排：计算 `llm_fit_score` 与 `llm_verdict`
- FR-06 前端筛选：支持关键词、来源、地区分类、Rule/AI筛选
- FR-07 详情展示：支持结构化描述与匹配理由
- FR-08 RSS输出：提供 all/high-match feed
- FR-09 调度运行：分钟级周期执行采集和重排

## 8.4 非功能需求（NFR）

- NFR-01 稳定性：单源失败不影响整体任务
- NFR-02 可观测性：日志包含 found/new/duplicates/errors
- NFR-03 可配置性：关键策略可由环境变量调整
- NFR-04 安全性：凭据通过环境变量与 secrets 管理
- NFR-05 可维护性：新增来源尽量不改核心管线

## 8.5 验收标准（简版）

- 页面可稳定显示非0数据（在数据库有数据时）
- 筛选条件与 API 结果一致
- LLM链路可按计划执行并回写
- RSS 输出无乱码
- 关键接口响应成功率满足发布要求

---

## 9. 当前已知风险与建议

1. **本地访问域名差异风险**
   - `localhost` 与 `127.0.0.1` 属于不同 origin
   - 建议测试脚本同时覆盖两者

2. **运行态不一致风险（构建期/运行期配置）**
   - 建议发布前固定 `docker compose build --no-cache` + `--force-recreate`

3. **AI筛选过严导致“误感知无数据”**
   - 建议测试时固定一组“宽松/严格”双配置对照

---

## 10. 建议的发版前执行命令（参考）

```bash
docker compose build --no-cache api worker frontend
docker compose up -d --force-recreate api worker frontend

curl -sS http://localhost:8000/healthz
curl -sS "http://localhost:8000/jobs/count?status=active&min_score=0"
curl -sS "http://localhost:8000/jobs/count?status=active&min_score=0&llm_verdict=strong_fit,possible_fit&min_llm_score=60"
curl -sS http://localhost:8000/sources/official
```

---

如果需要，我可以在这个文档基础上再补一版「测试记录模板」（含测试人、时间、环境、结果、缺陷编号）用于你正式走发布评审会。
