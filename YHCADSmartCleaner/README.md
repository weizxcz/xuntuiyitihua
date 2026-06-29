# YHCADSmartCleaner - CAD模型智能识别清理工具

## 项目概述

YHCADSmartCleaner是一个基于Python开发的、旨在为CAD/CAE工程师提供高效、易用的几何特征识别和清理工具。该平台集成了OCC几何引擎和GMSH网格引擎，支持多种几何特征识别、处理和可视化功能，助力工程师快速进行CAE前处理工作。

## 技术栈

- **编程语言**: Python 3.11
- **GUI框架**: wxPython 4.2.4
- **几何引擎**: Open CASCADE Community Edition (OCC) （炎核SDK）
- **网格引擎**: GMSH （炎核SDK）
- **渲染引擎**: Vulkan （炎核SDK）
- **AI特征识别**: AAGNet 模型

## 目录结构

```
YHCADSmartCleaner/
├── SDK/               # 炎核SDK
├── ai/                # AI特征识别模块
├── config/            # 配置文件管理
├── dialog/            # 对话框实现
├── function/          # 功能模块
├── icons/             # 图标资源
├── ui/                # UI组件
├── main.py            # 主入口文件
├── README.md          # 项目说明文档
└── requirements.txt   # 依赖列表
```

## 核心模块功能

### 1. 主入口 (main.py)
- 应用程序的启动点
- 初始化UI和核心组件
- 管理主窗口生命周期

### 2. AI特征识别模块 (ai/)
- 集成AAGNet 模型用于几何特征识别
- 实现圆角、倒角等特征的智能识别
- 提供模型推理和结果处理功能

### 3. 配置管理 (config/)
- `config_load.py`: 加载和管理系统配置
- `system_config.json`: 系统配置文件
- 负责全局配置的读取和应用

### 4. 对话框模块 (dialog/)
- `export_file.py`: 文件导出对话框
- `find_fillet.py`: 圆角查找对话框
- `import_file.py`: 文件导入对话框
- `new_assembly.py`: 装配文档创建对话框
- `new_document.py`: 新文档创建对话框
- `open_ncti_file.py`: NCTI文件打开对话框
- `save_ncit_file.py`: NCTI文件保存对话框
- `select_file_base.py`: 文件选择基础对话框
- `select_infer_method.py`: 推理方法选择对话框
- `show_features.py`: 特征列表对话框
- 提供各种功能的交互界面

###  功能模块 (function/)
- `mouse_event_delegate.py`: 鼠标事件委托处理
- `on_category_file.py`: 文件操作功能
- `on_find_cone.py`: 圆锥面查找功能实现
- `on_find_cylinder.py`: 圆柱面查找功能实现
- `on_find_fillet.py`: 圆角查找功能实现（几何属性算法）
- `on_find_fillet_by_ai.py`: 圆角查找功能实现（AI算法）
- `on_find_fillet_hyper.py`: 圆角查找功能实现（融合识别算法）
- `on_find_plane.py`: 平面查找功能实现
- `on_new_assembly.py`: 新装配文档创建功能
- `on_new_document.py`: 新文档创建功能
- `on_remove_feature.py`: 特征移除功能
- 实现平台的核心业务逻辑

###  UI组件 (ui/)
- `main_window.py`: 主窗口实现，包含整个应用的布局管理、事件绑定、菜单和工具栏等，是整个应用的核心UI组件
- `viewer.py`: 3D视图组件，负责显示3D模型视图，处理视图的嵌入、尺寸变化和更新等
- `property_panel.py`: 属性面板组件，用于显示和编辑对象的属性
- `assembly_panel.py`: 装配面板组件，用于显示装配体的层次结构
- 实现平台的用户界面组件，提供直观的交互体验

### 8. 图标资源 (icons/)
- 各种工具栏和按钮图标
- 提供清晰直观的视觉反馈

## 功能特性

### 几何特征识别
- AI驱动的圆角识别与清理
- 倒角识别与清理
- 孔识别与处理
- Logo特征识别

### 几何特征处理
- 特征高亮显示
- 特征批量处理
- 特征移除与修复

### 模型操作
- 模型导入导出（支持STP、STEP、IGS、NCTI格式）
- 模型可视化与渲染
- 多种视图模式切换
- 交互式操作

### 装配功能
- 装配文档创建
- 零件装配管理
- 装配关系可视化

## 模块依赖关系

```
main.py
├── ui/main_window.py
│   ├── dialog/              # 各种对话框
│   ├── ui/viewer.py         # 3D视图组件
│   └── ui/property_panel.py # 属性面板
├── function/                # 功能实现
│   ├── ai/                  # AI特征识别
│   └── interface/           # 底层接口
│       └── SDK/             # 第三方库
└── config/config_load.py     # 配置管理
```

## 安装与运行

### 环境要求
- Windows 10/11 64位系统
- Python 3.8+

### 安装步骤

1. **创建虚拟环境**
   ```bash
   python -m venv .venv
   ```

2. **激活虚拟环境**
   ```bash
   .venv\Scripts\activate
   ```

3. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

4. **运行应用程序**
   ```bash
   python main.py
   ```

## 使用说明

### 1. 创建新文档
   - 点击"文件"选项卡
   - 点击"创建零件"或"创建装配"按钮
   - 在对话框中选择几何引擎、约束引擎和网格引擎
   - 点击"确定"创建新文档

### 2. 导入CAD模型
   - 点击"文件"选项卡
   - 点击"导入零件"按钮
   - 选择要导入的CAD文件（支持STP、STEP、IGS格式）
   - 点击"打开"导入模型

### 3. 识别几何特征
   - 点击"AI"选项卡
   - 选择相应的特征识别工具（如"AI圆角识别"）
   - 选择推理方法
   - 系统将自动识别并高亮显示相关特征
   - 可在特征列表中查看和处理识别结果

### 4. 特征处理
   - 在特征列表中选择要处理的特征
   - 点击"移除特征"按钮
   - 系统将自动移除所选特征并更新模型

### 5. 模型导出
   - 点击"文件"选项卡
   - 点击"导出模型"按钮
   - 选择导出格式（支持IGS、STP、STEP、BREP、SAT、PRT）
   - 点击"保存"导出模型

## 开发指南

### 代码规范
- 遵循PEP 8代码风格
- 函数和类采用清晰的命名规范
- 为公共函数和类添加文档字符串
- 使用类型注解提高代码可读性

### 扩展功能

要添加新功能，建议按照以下步骤进行：

1. 在`function/`目录下创建新的功能实现文件
2. 在`dialog/`目录下创建相应的对话框
3. 在`interface/`目录下封装底层SDK调用
4. 在UI中添加相应的菜单或工具栏按钮
5. 绑定事件处理函数

### 调试技巧

- 利用IDE的调试功能进行断点调试
- 查看日志文件了解系统运行状态
- 使用PyInstaller进行打包测试

## 构建与部署

### 打包应用程序

使用PyInstaller打包应用程序：

```bash
pyinstaller --name=SmartClearner --windowed --icon=icons/ncti.ico --onedir  main.py --add-data=icons:icons --add-data=SDK:SDK --add-data=config/system_config.json:config

debug version:
pyinstaller --name=SmartClearner --icon=icons/ncti.ico --onedir main.py --add-data=icons:icons --add-data=SDK:SDK --add-data=config/system_config.json:config --add-data=ai/AAGNet_infer/weights:ai/AAGNet_infer/weights --hidden-import=scipy._lib.array_api_compat.numpy.fft --hidden-import=scipy._lib.array_api_compat.numpy --hidden-import=scipy._lib.array_api_compat

release version:
pyinstaller --name=SmartClearner --windowed --icon=icons/ncti.ico --onedir main.py --add-data=icons:icons --add-data=SDK:SDK --add-data=config/system_config.json:config --add-data=ai/AAGNet_infer/weights:ai/AAGNet_infer/weights --hidden-import=scipy._lib.array_api_compat.numpy.fft --hidden-import=scipy._lib.array_api_compat.numpy --hidden-import=scipy._lib.array_api_compat --hidden-import=scipy.special._special_ufuncs

```

### 打包注意事项

- 确保所有依赖已正确安装
- 检查配置文件路径是否正确
- 测试打包后的应用程序在目标环境中能否正常运行

## 更新日志

### v1.0.0 (2025-12-09)
- 初始版本发布
- 支持基本的几何特征识别功能
- 实现基本的3D可视化
- 提供多种对话框和功能模块

### v1.1.0 (2025-12-12)
- 新增装配文档创建功能
- 完善UI布局和交互体验
- 修复文件对话框兼容性问题

### v1.2.0 (2025-12-17)
- 集成AAGNet模型进行AI特征识别
- 新增推理方法选择功能
- 完善对话框实现，替换PyQt5为wxPython
- 新增模型导入导出功能

## 致谢

感谢以下开源项目和社区的支持：

- [炎核多内核CAD/CAE-培训中心](https://opencax.cn/gmde/knowledge/index)
- [炎核多内核CAD/CAE开发平台](https://opencax.cn/gmde/download)
- [wxPython](https://www.wxpython.org/)
- [AAGNet](https://github.com/bytedance/AAGNet)

---

**YHCADSmartCleaner - 让CAE前处理更简单、更高效！**