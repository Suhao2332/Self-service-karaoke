# 自助卡拉OK制作器

一个基于Python PyQt6的桌面应用，可以将普通MV视频转换为带有卡拉OK字幕效果的视频。

## 项目结构

```
self-service-karaoke/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # 桌面应用入口
│   │   ├── ui/
│   │   │   ├── __init__.py
│   │   │   └── main_window.py   # 主窗口（简洁流程式UI）
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── audio_processor.py   # 音频提取（FFmpeg）
│   │   │   ├── lyrics_fetcher.py    # 歌词获取（网易云+QQ+酷狗3源并行）
│   │   │   ├── timeline_aligner.py  # 时间轴对齐（librosa节拍检测）
│   │   │   └── karaoke_renderer.py  # 卡拉OK渲染（ASS字幕）
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── ffmpeg_helper.py     # FFmpeg环境检查
│   ├── tests/                   # 测试目录
│   │   ├── run_tests.py         # 完整测试脚本
│   │   ├── test_video.mp4       # 测试用视频
│   │   └── output/              # 测试输出
│   └── requirements.txt
└── README.md
```

## 核心功能

1. **视频上传**：选择MV视频文件后自动提取音频
2. **多源歌词搜索**：并行搜索网易云音乐、QQ音乐、**酷狗音乐**三大平台
3. **时间轴对齐**：librosa节拍检测 + 最近节拍对齐算法
4. **卡拉OK渲染**：生成带有逐字高亮效果的卡拉OK字幕视频（ASS格式）
5. **手动调整**：渲染后可微调字幕时间偏移

## 操作流程

简洁的3步操作：

```
1. 选择视频文件 →（自动提取音频）
2. 输入歌曲名称 + 歌手
3. 搜索歌词 → 渲染卡拉OK视频
```

UI采用流程式布局，顶部步骤指示器实时显示当前进度。

## 安装与运行

### 前置条件

- Python 3.8+
- FFmpeg（需添加到系统PATH）
- 网络连接（用于在线歌词搜索）

### 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 启动应用

```bash
cd backend
python -m app.main
```

### 运行测试

```bash
cd backend
python tests/run_tests.py
```

## 技术栈

- **桌面框架**：PyQt6
- **音频处理**：librosa + FFmpeg
- **歌词获取**：网易云音乐 / QQ音乐 / 酷狗音乐（3源并行搜索）
- **字幕格式**：ASS（Advanced SubStation Alpha）

## 歌词搜索说明

歌词搜索会**并行查询**三个平台，即使某个平台不可用也不影响其他平台：

| 平台 | 协议 | 备注 |
|------|------|------|
| 网易云音乐 | HTTPS | 需要正常网络 |
| QQ音乐 | HTTPS | 需要正常网络 |
| 酷狗音乐 | **HTTP** | 部分代理环境仍可用 |

搜索失败时会明确提示原因（网络错误 / 歌曲不存在 / 无歌词数据）。

## 注意事项

1. **FFmpeg**：必须安装并确保在命令行中可用（[下载地址](https://ffmpeg.org/download.html)）
2. **歌词源**：部分音乐平台可能有限制，3源并行提高成功率
3. **性能**：处理大视频文件可能需要较长时间

## 后续优化方向

1. **更多歌词格式**：支持SRT、SSA等格式
2. **多语言支持**：支持中英文双语歌词
3. **批量处理**：支持多个视频批量处理
4. **GPU加速**：使用CUDA加速视频渲染

## 许可证

MIT License
