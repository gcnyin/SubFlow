# SubFlow 设计决策记录

> 本文档记录 SubFlow 项目的所有架构和设计决策，共 37 项。

---

## 产品定位

| # | 决策 | 结论 |
|---|------|------|
| 1 | 用户/形态 | 本地 CLI 工具，面向个人创作者 |
| 2 | ASR 引擎 | faster-whisper（本地离线） |
| 3 | 字幕输出类型 | 纯文本字幕文件（不做烧录） |
| 4 | 字幕格式 | 默认 SRT，`--format vtt` 可切换 |
| 5 | 翻译功能 | v1 不做，架构预留 `Translator` 接口。v2（0.2.0）实现 |
| 6 | 对齐策略 | 词级对齐 + 智能拆分（最多 15 字 / 最多 3 秒，标点断开） |

## 处理管线

| # | 决策 | 结论 |
|---|------|------|
| 7 | 管线流程 | 音频提取(FFmpeg) → faster-whisper(VAD+词级时间戳) → 智能拆分 → SRT/VTT 输出 |
| 15 | 输入类型 | 视频 + 纯音频均支持，根据扩展名自动判断 |
| 16 | 多音轨 | 默认第一条音轨，`--audio-track` 指定，多音轨时打印 warning |
| 19 | 长视频 | 信任 faster-whisper 内置 VAD 分段，提供 `--max-duration` 限制 |
| 20 | 批量处理 | 支持多文件输入参数（`subflow *.mp4`），不做内置 batch 命令 |
| 21 | 中间产物 | 系统临时目录，用完即删，`--keep-audio` 保留 |

## 技术栈

| # | 决策 | 结论 |
|---|------|------|
| 8 | 编程语言 | Python 3.11+ |
| 9 | CLI 框架 | typer + rich（`typer[all]`） |
| 9 | 依赖管理 | uv |
| 10 | 目录结构 | src layout（`src/subflow/`） |
| 27 | 运行时依赖 | `faster-whisper` + `typer[all]`，仅 2 个 |
| 27 | FFmpeg 调用 | 标准库 `subprocess`，不引入 ffmpeg-python |
| 27 | 配置解析 | 标准库 `tomllib`（Python 3.11+），零额外依赖 |
| 29 | 开源协议 | MIT |
| 30 | 代码质量 | ruff（lint+format）+ mypy（类型检查）+ pre-commit hooks |
| 33 | CI/CD | v1 跳过 CI，本地手动 `ruff check && mypy && pytest` |
| 36 | 平台 | 代码跨平台，v1 主测 Linux（macOS/Windows 实验性） |

## ASR 引擎

| # | 决策 | 结论 |
|---|------|------|
| 11 | 语言检测 | 自动检测（faster-whisper 内置），`--lang` 手动覆盖 |
| 12 | 默认模型 | `medium`（平衡精度和速度） |
| 12 | 模型存储 | `~/.cache/subflow/models/`，`--model-dir` 覆盖 |
| 12 | 模型获取 | 首次运行自动下载，`subflow list-models` 查看可用模型 |
| 25 | 暴露参数 | 精选：`--model`、`--language`、`--beam-size`、`--device`，`--extra-args` 传 JSON |
| 26 | GPU 策略 | `--device auto` 检测 CUDA → 回退 CPU，启动时打印设备信息 |

## 输出

| # | 决策 | 结论 |
|---|------|------|
| 22 | 输出命名 | 默认同目录同名，`-o` 指定完整路径，`--output-dir` 指定目录 |

## 配置

| # | 决策 | 结论 |
|---|------|------|
| 13 | 配置文件 | `~/.config/subflow/config.toml`，CLI flag > 配置文件 > 硬编码默认值 |

## 用户体验

| # | 决策 | 结论 |
|---|------|------|
| 14 | 进度显示 | rich 分段日志 + 进度条 |
| 18 | 错误处理 | 友好错误信息，捕获常见错误，给出解决建议 |
| 31 | 日志/调试 | `-v`/`-vv` 控制日志级别，`--dump-json` 输出完整 transcript |
| 34 | FFmpeg 依赖 | 启动时检测 + 报错 + 安装指南（Ubuntu/Debian/Arch/Fedora/macOS/Windows） |

## 数据模型

| # | 决策 | 结论 |
|---|------|------|
| 28 | 核心模型 | `WordTimestamp`（词+时间戳+概率）+ `SubtitleItem`（索引+起止时间+文本+词列表） |

## 工程实践

| # | 决策 | 结论 |
|---|------|------|
| 17 | 管线抽象 | v1 写死为固定流程，v2 再考虑 Pipeline/Stage 抽象 |
| 23 | 测试 | pytest 单元测试 + 集成测试（tiny 模型 + 5 秒测试视频） |
| 24 | 分发方式 | v1: `git clone` + `uv sync`，后续 PyPI + `pipx install subflow` |
| 32 | 版本方案 | 严格 SemVer，起始 `0.1.0` |
| 35 | 文档 | 标准 README（200-300 行），v2 上 MkDocs |

---

## 里程碑规划

```
0.1.0 — 核心管线通（faster-whisper + SRT/VTT + 智能拆分）
0.2.0 — 翻译功能（多语言字幕）
0.3.0 — 烧录字幕（hardsub）
1.0.0 — 稳定 API + 完整文档 + PyPI 发布
```
