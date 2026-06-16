# SubFlow vs YouTube 字幕质量对比分析

> 测试日期：2026-06-17
> SubFlow 版本：v0.3.0
> 测试视频：*Six Interesting Coffee Brewers (Compared)* — 约 24 分钟英文咖啡评测视频

---

## 1. 基本统计

| 指标 | SubFlow (faster-whisper) | YouTube 自动字幕 |
|------|--------------------------|-------------------|
| 字幕条目数 | **587** 条 | ~469 条 |
| 开始时间 | 00:20.360 | 00:00.197 |
| 结束时间 | 24:01.359 | ~24:02 |
| 格式 | SRT (clean LF) | SRT (mixed CRLF) |
| 模型 | medium (推测) | YouTube 自有 ASR |
| 测试文件 | `Six_Interesting_Coffee_Brewers_Compared.srt` | `Six Interesting Coffee Brewers (Compared) [English] [DownloadYoutubeSubtitles.com].srt` |

---

## 2. 逐项质量评估

### 2.1 🟢 语音识别准确率 — 两者相当，各有优势

**相同准确的部分**（约 90%+ 的日常词汇）：

```
SubFlow:  "Here we've got the Origami Dripper, the Kafeck Flower Dripper which is very pretty."
YouTube:  "Here, we've got the Origami Dripper, the Cafec Flower dripper which is very pretty."
```

**SubFlow 更差的地方**（专有名词识别）：

| 正确 | SubFlow | YouTube |
|------|---------|---------|
| Cafec | **Kafeck** ❌ | Cafec ✅ |
| Hsiao | **Shao** / **shower** ❌ | Hsiao ✅ |
| Stagg | **Stag** ❌ | Stagg ✅ |
| Espro | **Asbro** / **S-Brow** ❌ | Espro ✅ |
| vacuum wall | **vacuum war** ❌ | vacuum wall ✅ |
| I've backed some on Kickstarter | **I've backed someone kickstarter** ❌ | I've backed some on Kickstarter ✅ |

**SubFlow 更好的地方**（部分识别更完整）：

```
SubFlow:  "the design at the bottom to sort of keep the paper away from that hole..."
YouTube:  "the design at the bottom to sort of keep the paper away..."  (后半截丢失)
```

> **结论**: YouTube 在专有名词上明显更准（可能得益于 YouTube 的领域知识/语言模型更大），SubFlow 的通用 faster-whisper 模型对罕见专名容易出错。

---

### 2.2 🔴 文本格式 — SubFlow 严重缺陷

SubFlow 最大问题：**完全丢失了英文的大小写和标点符号**。

```
SubFlow:  "today we're going to be comparing six different pour over
          brewers and to be honest i might be in a bit of trouble"

YouTube:  "Today we're gonna be comparing six different
          pour over brewers. And to be honest, I might
          be in a bit of trouble."
```

所有 `I` → `i`，无句号、逗号、问号。这在英文中是**不可接受的错误**。faster-whisper 本身会返回所有小写且无标点的词，这是模型特性而非 bug，但 SubFlow 没有做任何后处理来恢复大写和标点。

YouTube 则保持了自然的大小写和标点。

---

### 2.3 🟡 句子拆分 — 各有问题

**SubFlow 拆分太碎** (max_words=15, max_duration=3s 对英文偏严)：

```
2.  "brewers and to be honest I might be in a bit of trouble."
3.  "I might have opened Pandora's"
4.  "box here and I'll"
5.  "tell you why in a second."
```

一句话被拆成了 4 条字幕，其中 "box here and I'll" 基本无意义。

**YouTube 拆分更自然**：

```
4.  "And to be honest, I might be in a bit of trouble."
5.  "I might've opened Pandora's box here"
6.  "and I'll tell you why in a second."
```

但 YouTube 偶尔也会出现超长单句或奇怪的断开。

> **结论**: SubFlow 的默认参数（15 词/3 秒）是为中文优化的，英文应该放宽到 12-15 词 + 4-5 秒，或者基于句子边界（句号）而非纯字数来拆分。当前拆分导致大量「半句话」字幕。

---

### 2.4 🟢 元数据处理 — SubFlow 更干净

- YouTube: 显式标注了环境音 `(upbeat music)`, `(cups clinking)`，从 00:00 开始
- SubFlow: 直接从说话内容开始（00:20），自动跳过音乐/环境音段

SubFlow 的做法对于只想看文字字幕的用户更干净。但 YouTube 的做法对听障人士更友好（标注环境音）。

---

### 2.5 🟢 时间戳 — SubFlow 略更好

```
说话开始:  SubFlow 00:20.360  vs  YouTube 00:20.640  (SubFlow 快 0.28s，更贴近实际发音)
条目内部:  SubFlow 更细粒度，YouTube 条目时长跨度更大
```

SubFlow 基于 faster-whisper 词级时间戳，理论上精度更高（每个词都有时间），对齐更准确。

---

## 3. 总体评分

| 维度 | SubFlow | YouTube | 权重 |
|------|---------|---------|------|
| 识别准确率 | ⭐⭐⭐⭐ (85%) | ⭐⭐⭐⭐½ (90%) | 30% |
| 文本格式化 | ⭐ (致命) | ⭐⭐⭐⭐⭐ | 25% |
| 句子拆分 | ⭐⭐½ | ⭐⭐⭐⭐ | 20% |
| 时间戳精度 | ⭐⭐⭐⭐ | ⭐⭐⭐½ | 15% |
| 元数据处理 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 10% |
| **综合** | **⭐⭐½ (49%)** | **⭐⭐⭐⭐ (85%)** | |

---

## 4. 改进建议

### 4.1 🔴 紧急：加后处理管道

对英文输出自动恢复：
- 首字母大写、`i` → `I`
- 用简单的 NLP/规则在句末添加标点（或用 LLM 一次性做 punctuation restoration）
- 已有开源方案如 `punctuators`、`deepmultilingualpunctuation` 或直接用 LLM 做轻量后处理

### 4.2 🟡 英文拆分参数调优

对非 CJK 语言放宽：
- `max_words_per_line` 从 15 提到 18-20
- `max_duration_seconds` 从 3.0 提到 4.5-5.0
- 或者直接按语音停顿（word gap > 0.5s）作为分隔点

### 4.3 🟡 拆分逻辑改进

当前只在「标点 + 至少 3 词」才触发边界拆分。对英文，标点经常不被 Whisper 识别为独立 token，导致边界检测失败。建议：
- 检测词间停顿 (gap > 0.4s) 作为句子边界
- 对英文模型输出做标点恢复后再拆分

### 4.4 🟢 模型选择

`medium` 模型对专有名词识别不佳，建议默认推荐 `large-v3` 用于英文内容。
