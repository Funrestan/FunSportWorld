<h1 style="font-size: 48px;">别倒卖了😭</h1>

# FunSportWorld

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-CC%20BY--NC%204.0-lightgrey)

运动世界校园版全协议自动化工具，Python 实现，支持桌面 GUI 和 CLI。

> ⚠️ **仅供学习研究，请勿用于违反学校规定的场景，后果自负。**

---

## 灵感来源与致谢

本项目的**路径规划算法**与**通讯协议构建**思路直接参考自：

- **[NekoSportsWorldTool](https://github.com/YanamiNeko/NekoSportsWorldTool)** — Rust 版全协议自动化工具，作者 [@YanamiNeko](https://github.com/YanamiNeko)。本项目在协议层、信封加密、轨迹生成器、卡路里公式等核心逻辑上完整移植自该项目。
- **[@L1Xu4n](https://github.com/L1Xu4n)** — 提出**接入地图 API 生成更真实道路**的改进方案，本项目据此实现了 `campus_loop.py`（用步行路径规划把打卡点连成闭合环）与 `--use-map` 模式，显著提升轨迹的道路贴合度。

**没有这两位的工作，本项目不可能存在。**

---

## 功能

- **跑步**：一键全链（策略 → 打卡点 → 校园环 → 轨迹 → 提交 → OBS → 验证），生成始终使用高德步行折线，规划失败即停止
- **AI 运动**：计次 / 计时双类型，批量补签（前 60 天 × 多项目）
- **数据**：学期完成度、违规自查、排行榜（个人/班级/院系 × 日/月、室内榜、历史榜）、个人主页
- **登录**：GT4 滑块验证自动通过
- **全自动**：`--auto` 一步完成（距离对齐学校要求 + 冗余、配速/步频随机、自动走真实路径）
- **时间窗口校验**：按最终方案检查有效时段；`--allow-outside` 只跳过本地检查，不能改变服务器限制
- **GUI 地图预览**：内嵌高德地图（`tkintermapview`），轨迹、打卡点、起终点直接叠加在地图上

---

## 技术特点

- 完整实现 **NetSecKit 信封加密**与响应解密，每个响应强制 RSA 验签（fail-closed）
- **GT4 滑块验证**全程本地完成（缺口识别 + PoW + AES/RSA 构造 w 参数），不依赖任何外部服务
- **轨迹生成器**：沿高德折线分配目标里程，规划样本不随机插入无效、越界或打卡事件；预览与上传共用坐标
- **道路路径环**：通过高德步行 API 把打卡点连成闭合环；校验路线缓存来源、顺序及有效期，不回退拟合环
- **GUI 地图**：`tkintermapview` + 高德瓦片（`style=8`，GCJ-02），轨迹 `set_path`、点位 `set_marker(icon=...)`，图标为 PIL 内存绘制（圆点/方块）
- 设备身份持久化（DeviceId / 安装时间 / MAC），稳定不易触发风控
- 本地缓存（点位 / AI 项目 / 校园环），减少接口调用，规避限流

---

## 环境要求

- **Python 3.8+**
- 网络能访问：
  - `run.gxapp.iydsj.com`（主服务）
  - `discovery.gxapp.iydsj.com`（排行榜）
  - `gcaptcha4.geetest.com`（GT4 验证码）
  - `restapi.amap.com`（高德路线和底图；没有有效路线缓存时为生成必需）
  - `webrd01.is.autonavi.com`（GUI 地图瓦片）
  - `api.ipify.org`（IP 检测，可选）

---

## 安装

```bash
# 1. 克隆或下载项目
cd FunSportWorld

# 2. 创建虚拟环境（推荐）
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt
```

**requirements.txt**：

```
pycryptodome>=3.19
requests>=2.31
Pillow>=10.0
numpy>=1.24
tkintermapview>=1.28
```

---

## 快速开始

Windows 可双击根目录的 `start-gui.cmd` 启动桌面 GUI，或运行 `python -m funsport gui`。启动窗口不会自动登录或提交记录。

- [GUI 使用与文件说明](docs/gui-guide.md)
- [打卡点兼容性与验证边界](docs/checkpoint-compatibility.md)
- [新增及改动函数说明](docs/functions.md)
- [路线闭合与预览一致性](docs/route-geometry.md)
- [不同道路与随机种子](docs/route-variation.md)

随机种子现同时参与道路选择和采样：0 自动取新种子，固定数字便于复现。路线缓存改为保存每段高德备选，换种子可在缓存中选另一组道路；不打乱打卡顺序。若高德每段都只返回一条，界面会明确提示，不能保证每次都换路。

已针对 App 7.3.70 的顺序模式补充点位顺序：policy=1 且整组缺少顺序时，按本次高德途经顺序编号；已有完整顺序沿用，异常或混合顺序拒绝猜测。请重启后重新生成预览，方案明细会显示处理来源。不会改写通过状态或已上传记录，不保证适用于所有版本和学校策略。

打卡点显示已有使用者反馈恢复；路线完整性与备选道路选择通过了离线回归，未据此宣称所有设备均已实测。不要重复上传已有记录测试。

GUI 支持「在线预览 → 检查地图和明细 → 确认提交同一方案」。「跳过本地时间检查」只影响本地校验，不能越过服务器的 11016；只测试轨迹可使用当前账号缓存生成不可提交的「轨迹预览」。两种预览均使用高德步行路线，没有有效路线缓存时需要 Web 服务 Key。底图是独立请求，失败时仍可查看已生成轨迹。坐标优先使用原生 GCJ-02，并提示源双坐标冲突。不能把「详情读取成功」理解为「打卡验证通过」。

```bash
# 一次性初始化（交互式，引导配置账号/城市/坐标/高德Key/设备）
python -m funsport init

# 全自动跑一次（推荐）
python -m funsport run --auto

# 查看打卡点
python -m funsport points

# 查看跑步记录
python -m funsport records
```

---

## 使用

```text
python -m funsport init --user <手机号> --pass <密码> --city <城市> --key <高德Key>
python -m funsport login --remember                    # 无参数时从 config.json 读账号
python -m funsport run --auto                          # 一键跑步
python -m funsport run --dist 2.8 --pace 400 --use-map
python -m funsport ai --sport 1 --mode min --score 3
python -m funsport rank main --type 1 --sort 1
python -m funsport help                                # 全部命令
```

### 子命令一览

| 命令 | 说明 |
|------|------|
| `init` | 一次性初始化（账号/城市/坐标/高德Key/设备/提前量） |
| `login` | 登录（无参数时从 `config.json` 读账号） |
| `logout` | 请求服务器退出，确认成功后清理本地会话；失败保留凭据 |
| `points` | 查看整组打卡点 |
| `policy` | 查看跑步策略（学校要求 + 时间窗口） |
| `lbs-amap` | 配置高德 LBS Key |
| `loop-rebuild` | 强制重建校园环 |
| `config` | 查看/设置配置 |
| `run` | 跑步全链 |
| `ai-list` | AI 项目列表 |
| `ai` | AI 运动提交 |
| `ai-records` | AI 运动记录 |
| `ai-info` | AI 记录详情 |
| `records` | 跑步记录 |
| `record-info` | 跑步详情 |
| `semester` | 学期完成度 |
| `cheat` | 违规自查 |
| `rank` | 排行榜 |

### `run` 参数

```text
python -m funsport run \
  --dist 2.8                     # 固定距离 km
  --dist-min 2.7 --dist-max 3.2  # 距离范围随机
  --min-dist 2600                # 强制里程下限（米）
  --pace 400                     # 固定配速 秒/km
  --pace-min 360 --pace-max 480  # 配速范围随机
  --cadence 160                  # 固定步频 spm
  --cadence-min 140 --cadence-max 180
  --auto                         # 全自动（距离按学校要求+冗余）
  --use-map                      # 兼容参数；始终使用高德路线
  --before 60                    # 提交时间提前 60 分钟
  --ago 30                       # 30 分钟前开始
  --days-ago 1 --time 08:30      # 昨天 08:30 开始
  --allow-outside                # 仅跳过本地检查，不能绕过 11016
  --seed 42                      # 随机种子
```

---

## GUI

启动：

```bash
python -m funsport gui
```

地图页用 `tkintermapview` 内嵌高德瓦片，操作按钮：

- **读取点位** — 拉取整组打卡点，地图上按顺序显示为橙色圆点 + 白色编号
- **在线预览** — 完整链生成方案（访问策略 / 点位 / 高德），显示轨迹与起点「起」、终点「终」
- **轨迹预览** — 只用本地缓存点位 + 高德路线，不访问运动服务，不可提交
- **加载底图** — 刷新当前视野的瓦片
- **↔** — 自适应全部点位与轨迹
- **+ / −** — 缩放

地图绘制说明：

| 元素 | 样式 |
|------|------|
| 轨迹 | 绿色粗线（`#00c18b`，和 Canvas 版原样式一致） |
| 打卡点 | 橙棕色实心圆 + 白色编号（Canvas 版原样式） |
| 起点 | 绿色方块 + 白色「起」 |
| 终点 | 红色方块 + 白色「终」 |

底图使用高德 `style=8` 瓦片（GCJ-02），与轨迹坐标系一致，无需坐标转换。

---

## 青龙定时任务

首次手工 `init`（或 `login --remember`）一次，之后定时挂 `run --auto` 即可。

`config.json` 里保存了账号和密码，会话失效时会自动重登。

---

## 常见问题

- **提示未登录 / 401**：`config.json` 里没账号密码，先执行 `init` 或 `login --remember`
- **10121 设备风险**：设备身份持久化在 `identity.json`，删除等于换新设备，不要频繁删
- **10603 点位限流**：点位接口 5 分钟限 3 次，内置 300s 缓存，正常使用不会触发
- **榜单为空**：当天还没有人产生有效里程，查询会自动回退最近 3 天
- **GT4 验证失败**：自动重试 3 轮，仍失败大概率是网络波动，稍后再试
- **开始时间不在窗口内**：本地检查按 `valid_time` 拒绝；`--allow-outside` 只跳过本地检查，服务器仍可返回 11016。只看轨迹可用缓存点位生成不可提交的预览
- **高德路径失败**：检查 Key、权限、额度和网络后重新规划。所有生成入口均不降级到拟合环
- **GUI 地图不出来**：确认 `tkintermapview>=1.28` 已安装；高德瓦片被墙时可临时把 `set_tile_server` 换成 OSM 测试
- **GUI 图标仍是默认水滴**：检查 `tkintermapview` 版本，`set_marker(..., icon=photo)` 必须创建时传 icon；旧版本 `change_icon` 会报 `marker needs icon image in constructor`
- **密码输入不显示**：`getpass` 设计如此，PyCharm Run 窗口可能不生效，用系统终端跑

---

## 目录结构

```
FunSportWorld/
├── README.md
├── LICENSE
├── requirements.txt
├── funsport/
│   ├── main.py              CLI 入口
│   ├── config.py            配置/身份/会话持久化
│   ├── gui.py               桌面 GUI
│   ├── gui_services.py      GUI 适配层
│   ├── map_preview.py       旧静态底图（GUI 已不依赖）
│   ├── logger.py            日志
│   ├── crypto/              信封加密 / 解密 / 头 / 签名
│   ├── api/                 业务接口
│   ├── track/               轨迹生成
│   └── cli/                 子命令
└── .funsport/               数据目录（首次运行创建）
    ├── config.json
    ├── identity.json
    ├── session.json
    ├── points_cache.json
    ├── ai_sports.json
    └── campus_loop_bd.json
```

---

## 版本

- **v0.2.0**：补齐 GUI 地图依赖，统一项目版本号与依赖清单。
- **v0.1.1** — GUI 地图迁移到 `tkintermapview`（高德瓦片）；修复定位点不贴合实际等问题
- **v0.1.0** — 添加图形化界面，处理检查点消失问题等
- **v0.0.1** — 初始版本，CLI 全链，时间安全性校验，历史记录自动登录

---

## 致谢

- **[NekoSportsWorldTool](https://github.com/YanamiNeko/NekoSportsWorldTool)** — 本项目的协议层、轨迹生成器、卡路里公式等核心逻辑完整移植自此
- **[@L1Xu4n](https://github.com/L1Xu4n)** — 提出接入高德地图 API 实现真实道路的改进方案

---

## 许可证

[CC BY-NC 4.0](LICENSE) — 署名 · 非商业性使用
禁止将本作品或其衍生作品用于任何商业目的（包括但不限于出售、收费代做、广告变现、集成到商业产品）。

使用、分发、修改本作品时必须注明原作者及本项目地址。
