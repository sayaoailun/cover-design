# Cover Design Generator

封面设计生成工具 - 批量生成书籍封面图片

## 功能特性

- **批量生成**：从 Excel 文件读取数据，批量生成封面图片
- **多语言支持**：支持中文、英文、日文、韩文、德文、法语、泰语等多种语言版本
- **布局模板**：支持横版（landscape）和竖版（portrait）两种布局
- **视觉效果**：
  - Studio Shadow 阴影效果
  - Reflection 倒影效果
  - Logo 和水印叠加
- **GUI 界面**：直观的图形界面，支持预览和日志查看
- **配置驱动**：通过 JSON 配置文件灵活调整各项参数

## 项目结构

```
coverdesign/
├── main.py              # 主程序入口（竖版布局）
├── main-vertical.py     # 竖版布局版本
├── main-testing.py      # 测试版本
├── config.json          # 主配置文件
├── config-vertical.json # 竖版配置文件
├── config-testing.json  # 测试配置文件
├── ISBN.xlsx            # Excel 数据源
├── requirements.txt     # 依赖列表
├── cover/               # 原始封面图片目录
├── materials/           # 素材目录（背景图、水印、语言版本标识等）
├── Output/              # 输出目录
└── *.ttc                # 字体文件
```

## 安装依赖

```bash
pip install -r requirements.txt
```

依赖项：
- Pillow >= 10.0.0
- pandas >= 2.0.0
- openpyxl >= 3.0.0

## 使用方法

### 1. 准备数据

编辑 `ISBN.xlsx` 文件，包含以下列：
- ISBN：书籍 ISBN 号
- 主标题：书籍主标题
- 副标题：书籍副标题（可选）
- 文版：语言版本（如：中文、英文、日文、韩文、德文、法语、泰国版）

### 2. 准备封面图片

将原始封面图片放入 `cover/` 目录，命名格式为 `{ISBN}.jpg`

### 3. 运行程序

```bash
python main.py
```

### 4. 界面操作

1. 设置 Excel 文件路径、Cover 目录、素材目录
2. 选择布局模板（竖版/横版）
3. 设置输出目录
4. 调整 JPG 输出质量（10-100）
5. 点击「开始生成」按钮
6. 查看预览和日志

## 配置文件说明

`config.json` 包含以下配置项：

- `canvas`: 画布尺寸配置
- `cover`: 封面图片位置和尺寸配置
- `text`: 文字样式配置（标题、副标题）
- `shadow`: 阴影效果配置
- `reflection`: 倒影效果配置
- `color_adjust`: 颜色调整配置
- `output`: 输出格式和质量配置
- `paths`: 文件路径配置
- `layouts`: 布局模板配置
- `version_map`: 语言版本映射

## 支持的语言版本

| 文版值 | 对应素材文件 |
|--------|--------------|
| 中文 | 中文.png / 中文-portrait.png / 中文-landscape.png |
| 英文 | 英文.png / 英文-portrait.png / 英文-landscape.png |
| 日文 | 日文.png / 日文-portrait.png / 日文-landscape.png |
| 韩文 | 韩文.png / 韩文-portrait.png / 韩文-landscape.png |
| 德文 | 德文.png / 德文-portrait.png / 德文-landscape.png |
| 法语 | 法语版.png / 法语版-portrait.png / 法语版-landscape.png |
| 泰国版 | 泰国版.png / 泰国版-portrait.png / 泰国版-landscape.png |

## 输出格式

支持 JPG/JPEG 和 PNG 格式，默认输出 JPG 格式，质量可调节。

## 注意事项

1. 确保 `cover/` 目录中的图片文件名与 Excel 中的 ISBN 号一致
2. 字体文件需放置在项目根目录或系统字体目录
3. 输出目录不存在时会自动创建
4. 生成过程中可随时停止

## 许可证

MIT License