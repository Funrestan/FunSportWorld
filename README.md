<h1 style="font-size: 48px;">别倒卖了😭</h1>

# FunSportWorld

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-CC%20BY--NC%204.0-lightgrey)

运动世界校园版全协议自动化工具，Python 实现，CLI 模式。

> ⚠️ **仅供学习研究，请勿用于违反学校规定的场景，后果自负。**

---

## 灵感来源与致谢

本项目的**路径规划算法**与**通讯协议构建**思路直接参考自：

- **[NekoSportsWorldTool](https://github.com/YanamiNeko/NekoSportsWorldTool)** — Rust 版全协议自动化工具，作者 [@YanamiNeko](https://github.com/YanamiNeko)。本项目在协议层、信封加密、轨迹生成器、卡路里公式等核心逻辑上完整移植自该项目。
- **[@L1Xu4n](https://github.com/L1Xu4n)** — 提出**接入地图 API 生成更真实道路**的改进方案，本项目据此实现了 `campus_loop.py`（用步行路径规划把打卡点连成闭合环）与 `--use-map` 模式，显著提升轨迹的道路贴合度。

**没有这两位的工作，本项目不可能存在。**

---

## 功能

- **跑步**：一键全链（策略 → 打卡点 → 校园环 → 轨迹 → 提交 → OBS → 验证），轨迹可走「真实道路」或「数学拟合环」，开始时间支持随机或指定到前 3 天
- **AI 运动**：计次 / 计时双类型，批量补签（前 60 天 × 多项目）
- **数据**：学期完成度、违规自查、排行榜（个人/班级/院系 × 日/月、室内榜、历史榜）、个人主页
- **登录**：GT4 滑块验证自动通过
- **全自动**：`--auto` 一步完成（距离对齐学校要求 + 冗余、配速/步频随机、自动走真实路径）
- **时间窗口校验**：开始时间不在学校允许的时间段内直接拒绝提交（可 `--allow-outside` 强制）

---

## 技术特点

- 完整实现 **NetSecKit 信封加密**与响应解密，每个响应强制 RSA 验签（fail-closed）
- **GT4 滑块验证**全程本地完成（缺口识别 + PoW + AES/RSA 构造 w 参数），不依赖任何外部服务
- **轨迹生成器**：速度曲线（ramp / 疲劳 / 正弦波 / 凹陷）+ AR(1) GPS 抖动 + 哨兵点 / 断崖 / 点位吸附
- **真实路径环**：通过高德步行 API 把打卡点连成闭合环，轨迹贴真实路网（`--use-map` / `--auto`）
- 设备身份持久化（DeviceId / 安装时间 / MAC），稳定不易触发风控
- 本地缓存（点位 / AI 项目 / 校园环），减少接口调用，规避限流

---

## 环境要求

- **Python 3.8+**
- 网络能访问：
  - `run.gxapp.iydsj.com`（主服务）
  - `discovery.gxapp.iydsj.com`（排行榜）
  - `gcaptcha4.geetest.com`（GT4 验证码）
  - `restapi.amap.com`（高德路线，可选）
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
```

---

## 快速开始

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
| `logout` | 登出 |
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
  --use-map                      # 用真实路径环
  --before 60                    # 提交时间提前 60 分钟
  --ago 30                       # 30 分钟前开始
  --days-ago 1 --time 08:30      # 昨天 08:30 开始
  --allow-outside                # 允许在有效时间窗口外提交
  --seed 42                      # 随机种子
```

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
- **开始时间不在窗口内**：`policy` 返回的 `valid_time` 是学校允许的时间段，不在则拒绝提交；可加 `--allow-outside` 强制
- **高德路径失败**：Key 无效或额度用完，重新 `lbs-amap --key` 配置；或退化为不用 `--use-map` 的拟合环模式
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

## 致谢

- **[NekoSportsWorldTool](https://github.com/YanamiNeko/NekoSportsWorldTool)** — 本项目的协议层、轨迹生成器、卡路里公式等核心逻辑完整移植自此
- **[@L1Xu4n](https://github.com/L1Xu4n)** — 提出接入高德地图 API 实现真实道路的改进方案

---

## 许可证

[CC BY-NC 4.0](LICENSE) — 署名 · 非商业性使用
禁止将本作品或其衍生作品用于任何商业目的（包括但不限于出售、收费代做、广告变现、集成到商业产品）。

使用、分发、修改本作品时必须注明原作者及本项目地址。