# 打卡点兼容性

## 数据与显示

轨迹线与打卡点是两条独立数据链：轨迹保存在run_data，点位保存在fixed_point_json；后者解码后是PointJsonEntity形式的包装，内层fivePointJson仍是列表字符串。上传成功或详情可读取，不等于App已显示点位或服务端已确认通过。

对Android 7.3.70的静态分析显示，历史地图在policy=1顺序分支中按position排序，遇到999提前结束点位绘制。position是路线序号，不是数据库id；isPass决定通过状态，不能用强制写true来修复序号缺失。

## 实现约束

- prepare_checkpoint_order仅在policy=1时处理顺序。全部缺失、null或999时，按即将用于高德规划的途经列表从0编号；已有完整零起始编号时沿用并排序。
- 部分缺失、重复、非连续、非整数或超过当前编号图标范围时拒绝猜测。其他整数policy保持点位顺序和字段。
- 点位坐标优先使用有效GCJ-02，再派生一致的BD-09。无有效坐标时停止；不把占位坐标当作真实位置。
- 预览、HTTP和OBS使用同一冻结包装。提交前检查快照与包装一致，旧999方案必须重新生成，不能在用户确认之后偷偷改变路线。
- 编号与序列化函数仍保留源字段。生成新的顺序跑方案时，独立判点阶段清除缓存中的旧isPass，按本次采样重新判定；id、state、isFixed保持不变，不改变学校policy或已上传记录。

关键实现：funsport/run_plan.py、funsport/track/wire.py、funsport/api/flow.py、funsport/coordinates.py、funsport/track/checkpoints.py。字段诊断入口在funsport/diagnostics.py。

## 顺序点状态与完成条件

2026-09-24的修改将判点接在轨迹生成之后、RunPlan冻结之前。policy=1按顺序推进；policy=0扫描所有未通过点并允许任意顺序，每个合格定位最多推进一个目标。顺序模式普通到点样本标记type=2；随机模式普通点标记type=1、固定点标记type=2。起点5、终点6不参与判点，恢复8/9保留特殊类型。无效、暂停、普通围栏外或配速不合格的样本不能推进目标。围栏优先使用策略中的geoFence，并按runAreaId选择对应围栏。

MyLocation.speed改为分钟/公里，avgSpeed为米/秒；依据最终坐标和定位时间重算，距离向上取到厘米。判点使用未舍入配速，避免保存到两位小数后改变2分钟/公里的边界。学校平均配速限制与这一定位门槛不同。

旧顺序客户端的本地完成条件包括最低记录时长、所有顺序点、学校minRunTime和距离；随机客户端要求固定点及至少两个普通点，并同样检查距离、记录时长和学校minRunTime。随机模式的时长门槛在轨迹生成阶段纳入，点位配额在生成后立即复核；不满足时不冻结可提交方案。提交前仍会与冻结快照核对。policy=2终点跑需要原生终点围栏判定，当前仍不生成可提交方案。学校配速、步频等后台规则仍以详情响应为准。

判点复制输入，更新后的points、fivePointJson及OBS fixed_point_json保持一致。已冻结方案不会自动重算；更新程序后需要重新生成并检查新方案。

## 诊断归档

开启现有通信归档选项后，`.funsport/data/run-diagnostics/<本次目录>/`新增：

- `checkpoint_evaluation.json`：逐样本目标、时间、原始配速、距离、判过或跳过原因，以及实际生成的到点事件。
- `completion.json`：本地完成规则、原因码和已知假设。
- `checkpoint_report.json`：服务端reasonList、提交点位与本地OBS点位的联合诊断。

详情点位为空且jsonFromObs=1时，诊断仍会比较本次本地提交与OBS包装；不会将本地OBS一致冒充远端对象已验证。服务端顶层complete=true与顺序规则失败会分别显示。

## 验证边界

点位显示已有使用者反馈恢复，不能推广为所有App版本、学校或模式均已验证。部分App地图桥接实现仍不透明；服务端有效性判定也不等同于客户端图标显示。

原生SportJniUtils.isValidPoint及部分新上传方法尚未恢复。当前模型明确记录native_validity_verified=false，沿用生成采样的有效性分类；它是已恢复Java规则的本地模拟，不代表完整官方引擎或服务端判定。没有生成SDK遥测或自动重传历史记录。

测试使用虚构点位与隔离目录，覆盖顺序推进、不能追认提前到点、重叠目标每次只推进一个、25米和配速边界、围栏与恢复分支、清除旧通过状态、冻结和重复提交保护，以及HTTP/OBS包装往返一致性。没有借助真实账号提交记录作为自动测试。

定向验证：python -m unittest -v tests.test_checkpoint_evaluation tests.test_location_pace tests.test_completion tests.test_checkpoint_order tests.test_diagnostics。

07:39归档离线重放验证：原始五个isPass全为false；采用归档策略围栏后，新模型在第5、72、453、589、872秒依次判过五点，本地complete=true、unCompleteReason=0，提交与解压OBS点位包装一致。验证只在内存中运行，原始归档和远端记录未改写。

排查时只比较已有记录的App版本、policy、点位数量和position分布。不要分享密码、token、会话文件、原始抓包或带签名的对象地址，不要为验证重复上传旧记录。
