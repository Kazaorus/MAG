# MAG

基于 MAA_FrameWork 框架的 深空之眼 自动化小助手，主要功能集中在每日任务的自动化

~~自动战斗先等孩子把YOLO用明白了再做~~
## 叠甲
1. 该项目是一个编程新手的第一个开源项目，可能包含以下要素：
	- 莫名其妙的函数调用
	- 嵌套好几层的循环
	- 不明所以的自定义动作
	- 奇怪的编程习惯
	- 屎山所具有的其他任何可能的要素
2. 由于一些原因，平常的空余时间较少，可能无法对该项目进行及时的维护和更新
3. 考虑到一般二游的运营和众多二游脚本的存续情况来看，勇士没有封禁脚本的理由。但若确实因为使用此脚本被封号，本人不承担任何责任

综上，欢迎各位发Issues和PR进行指导和修改，如果有比较复杂的需求或疑问，可以加QQ：1916860236

*我对自己项目的质量和大眼这游戏的热度还是有点数的QwQ要是建群估计没几个人。此外，由上面所说，平常比较忙，可能会忽略一些信息，能用Issue解决的尽量用Issue*

PS：原本的命名想法是将MAA里的Arknights换成AetherGazer，结果发现名字变成了~~某个奇怪的口号~~，于是就改成了这样

---
## 主要功能

- 启动/关闭游戏
- 收取定时体力补给/商店免费体力
- 公会相关任务
- 弥弥观测站
- 游园街收菜
- 餐厅自动运营
- 自动扫荡
- 皮肤活动每日登录奖励
- 领取每日任务/通行证/邮件
- ~~自动训练室~~（鸽ing）

---
## 注意事项

1. 该脚本暂时只支持 **Windows**  ~~等孩子把多系统兼容整明白了再去兼容Mac和Linux~~
2. 只支持模拟器端（最好为MuMu），暂不支持桌面
3. **游园街·餐厅** 任务首次使用前，需要在 `custom_task_config\restaurant\player_status.json` 内配置玩家信息：`"level"`: 各个厨具的等级；`"menu_slots"`: 的菜品上架限制；`"warehouse_stock"`: 当前仓库的食材数量
	**目前 游园街·餐厅 Bug较多，等待重构，尽可能不要使用**
	**一定要配置！不然崩了别怪我**

---
## 图形化界面

### [MFW-PyQt6](https://github.com/overflow65537/MFW-PyQt6)

一个基于PyQt6的MAAFramework图形化操作界面
- 在`Release`中下载对应压缩包
- 解压后运行main.exe或者MFW.exe

---
## How to build

**如果你要编译源码才看这节，否则直接 [下载](https://github.com/Kazaorus/MAG/releases) 即可**

0. 完整克隆本项目及子项目

   ```bash
   git clone --recursive https://github.com/Kazaorus/MAG.git
   ```

1. 安装

   ```python
   python ./install.py
   ```

生成的二进制及相关资源文件在 `install` 目录下
## 开发相关
- [MaaFramework 快速开始](https://github.com/MaaAssistantArknights/MaaFramework/blob/main/docs/zh_cn/1.1-%E5%BF%AB%E9%80%9F%E5%BC%80%E5%A7%8B.md)

## 鸣谢

### 开源库

- [MaaFramework](https://github.com/MaaXYZ/MaaFramework)

	基于图像识别的自动化黑盒测试框架 | An automation black-box testing framework based on image recognition

	本项目的开发框架
- [MFW-PyQt6](https://github.com/overflow65537/MFW-PyQt6)

	一个基于PySide6的MAAFramework图形化操作界面

	本项目的前端界面
- [MSBA](https://github.com/overflow65537/MAA_SnowBreak)

	尘白禁区每日任务自动化 | Assistant For Snowbreak: Containment Zone

	本项目的部分代码（[ScreenShot.py](https://github.com/Kazaorus/MAG/blob/main/assets/custom/action/ScreenShot.py)）的来源
### 开发者

感谢以下开发者对本项目作出的贡献：

<a href="https://github.com/Kazaorus/MAG/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Kazaorus/MAG&max=1000" alt="Contributors to MAG"/>
</a>
