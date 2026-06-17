# MV卡拉OK制作器

一个基于Python FastAPI的Web应用，可以将普通MV视频转换为带有卡拉OK字幕效果的视频。

## 项目结构

```
mv-karaoke-maker/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI入口
│   │   ├── audio_processor.py   # 音频提取
│   │   ├── song_identifier.py   # 歌曲识别
│   │   ├── lyrics_fetcher.py    # 歌词获取
│   │   ├── timeline_aligner.py  # 时间轴对齐
│   │   └── karaoke_renderer.py  # 卡拉OK渲染
│   ├── uploads/                 # 上传文件目录
│   ├── outputs/                 # 输出文件目录
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── README.md
```

## 核心功能

1. **视频上传**：用户上传MV视频文件
2. **音频提取**：从视频中提取音频（使用FFmpeg）
3. **歌曲识别**：通过音频指纹识别歌曲信息（需配置API）
4. **歌词获取**：从网易云音乐等平台获取LRC格式歌词
5. **时间轴对齐**：将歌词时间轴与音频节拍对齐
6. **卡拉OK渲染**：生成带有逐字高亮效果的卡拉OK字幕视频

## 安装与运行

### 前置条件

- Python 3.8+
- FFmpeg（需添加到系统PATH）
- 网络连接（用于歌曲识别和歌词获取）

### 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 启动服务

```bash
uvicorn app.main:app --reload
```

### 访问界面

打开浏览器访问 `http://localhost:8000`

## 技术栈

- **后端**：FastAPI + Python
- **音频处理**：librosa + FFmpeg
- **前端**：原生HTML/CSS/JavaScript
- **字幕格式**：ASS（Advanced SubStation Alpha）

## 注意事项

1. **FFmpeg**：必须安装FFmpeg并确保在命令行中可用
2. **API密钥**：歌曲识别模块需要注册Shazam API或其他音频识别服务
3. **歌词源**：网易云音乐API可能需要处理反爬虫机制，建议使用稳定的歌词API
4. **性能**：处理大视频文件可能需要较长时间，建议使用GPU加速

## 后续优化方向

1. **手动调整功能**：允许用户手动修正歌曲信息和歌词时间轴
2. **更多歌词格式**：支持SRT、SSA等格式
3. **多语言支持**：支持中英文双语歌词
4. **批量处理**：支持多个视频批量处理
5. **GPU加速**：使用CUDA加速视频渲染

## 许可证

MIT License
