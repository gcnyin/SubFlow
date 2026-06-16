# SubFlow — AI 视频字幕生成

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

🎬 自动从视频/音频生成 SRT/VTT 字幕。基于 faster-whisper，支持词级对齐和智能拆分。

## 功能

- **自动语音识别** — 基于 faster-whisper，支持 99+ 语言
- **词级时间戳** — 每个词都有精确的开始/结束时间
- **智能拆分** — 自动按句子边界、字数和时长拆分字幕行
- **本地离线** — 基于 faster-whisper，无需网络，隐私安全
- **多语言检测** — 自动识别语言，也可手动指定
- **SRT + VTT** — 两种最通用的字幕格式
- **批量处理** — 支持多文件同时处理

## 安装

### 前置要求

- **Python 3.11+**
- **uv** — Python 包管理器: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **FFmpeg** — 音频处理:
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - Arch Linux: `sudo pacman -S ffmpeg`
  - Fedora: `sudo dnf install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Windows: `winget install ffmpeg` 或访问 [ffmpeg.org](https://ffmpeg.org/download.html)

### 安装 SubFlow

```bash
git clone https://github.com/user/SubFlow.git
cd SubFlow
uv sync
```

## 快速开始

```bash
# 生成中文字幕（自动检测语言）
uv run subflow video.mp4

# 生成英文字幕
uv run subflow video.mp4 --lang en

# VTT 格式
uv run subflow video.mp4 --format vtt

# 指定输出路径
uv run subflow video.mp4 -o ./subs/my-subtitle.srt

# 批量处理
uv run subflow *.mp4

# 处理纯音频
uv run subflow podcast.mp3

# 使用更大的模型获得更高精度
uv run subflow video.mp4 --model large-v3
```

## CLI 参数

```
Usage: subflow [OPTIONS] FILES...

参数:
  FILES...               视频或音频文件（支持多个）

模型选项:
  --model, -m TEXT       模型大小: tiny/base/small/medium/large-v3 (默认: medium)
  --lang, -l TEXT        语言代码 (zh/en/ja/...) 或留空自动检测
  --beam-size INT        束搜索宽度 (默认: 5)
  --device TEXT          计算设备: auto/cpu/cuda (默认: auto)
  --model-dir TEXT       模型存储目录

输出选项:
  --format, -f TEXT      字幕格式: srt/vtt (默认: srt)
  --output, -o TEXT      输出文件路径
  --output-dir TEXT      输出目录

音频选项:
  --audio-track INT      音轨索引 (默认: 0)
  --keep-audio TEXT      保留提取的音频到指定路径

处理选项:
  --max-duration FLOAT   最大处理时长（秒）
  --max-words INT        每行字幕最大词数 (默认: 15)
  --max-line-duration FLOAT  每行字幕最大时长/秒 (默认: 3.0)

调试选项:
  -v, --verbose          详细输出 (-v 信息, -vv 调试)
  --dump-json            输出完整 transcript 到 JSON 文件
  --config, -c TEXT      配置文件路径

其他命令:
  subflow list-models    列出可用的 Whisper 模型
```

## 配置

创建 `~/.config/subflow/config.toml` 设置默认参数（CLI flag 优先级更高）：

```toml
# ~/.config/subflow/config.toml
model = "medium"
default_format = "srt"
max_words_per_line = 15
max_duration_seconds = 3.0
```

## 管线流程

```
输入文件 (视频/音频)
    │
    ├─ 🎵 音频提取 (FFmpeg → 16kHz mono WAV)
    │
    ├─ 🧠 语音识别 (faster-whisper + 词级时间戳)
    │
    ├─ 📐 智能拆分 (按句子边界/字数/时长)
    │
    └─ 📝 字幕输出 (SRT / VTT)
```

## 常见问题

**Q: 处理速度很慢？**
A: 如果有 GPU，SubFlow 会自动使用 CUDA 加速（快 3-10 倍）。CPU 用户可尝试更小的模型：`--model small` 或 `--model tiny`。

**Q: 模型放哪？**
A: 首次运行自动下载到 `~/.cache/subflow/models/`。可用 `--model-dir` 自定义。

**Q: 字幕不准确怎么办？**
A: 尝试更大的模型：`--model large-v3`，或手动指定语言：`--lang zh`。

**Q: 长视频内存不够？**
A: 使用 `--model small` 减少显存占用，或用 `--max-duration 600` 分段处理。

## 开发

```bash
# 安装依赖
uv sync

# 运行测试
uv run pytest

# 代码检查
uv run ruff check
uv run mypy

# 安装 pre-commit hooks
uv run pre-commit install
```

## 路线图

- [x] 0.1.0 — 核心管线（faster-whisper + SRT/VTT + 智能拆分）
- [x] 0.2.0 — 翻译功能（多语言字幕）
- [ ] 0.3.0 — 烧录字幕（hardsub，FFmpeg 嵌入视频）
- [ ] 1.0.0 — 稳定 API + 完整文档 + PyPI 发布

## 许可

MIT License
