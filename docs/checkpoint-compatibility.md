# 打卡点兼容性

## 数据与显示

轨迹线与打卡点是两条独立数据链：轨迹保存在run_data，点位保存在fixed_point_json；后者解码后是PointJsonEntity形式的包装，内层fivePointJson仍是列表字符串。上传成功或详情可读取，不等于App已显示点位或服务端已确认通过。

对Android 7.3.70的静态分析显示，历史地图在policy=1顺序分支中按position排序，遇到999提前结束点位绘制。position是路线序号，不是数据库id；isPass决定通过状态，不能用强制写true来修复序号缺失。

## 实现约束

- prepare_checkpoint_order仅在policy=1时处理顺序。全部缺失、null或999时，按即将用于高德规划的途经列表从0编号；已有完整零起始编号时沿用并排序。
- 部分缺失、重复、非连续、非整数或超过当前编号图标范围时拒绝猜测。其他整数policy保持点位顺序和字段。
- 点位坐标优先使用有效GCJ-02，再派生一致的BD-09。无有效坐标时停止；不把占位坐标当作真实位置。
- 预览、HTTP和OBS使用同一冻结包装。提交前检查快照与包装一致，旧999方案必须重新生成，不能在用户确认之后偷偷改变路线。
- 保留源id、state、isFixed及布尔isPass，不根据几何距离自动补造通过事件；不改变学校policy或已上传记录。

关键实现：funsport/run_plan.py、funsport/track/wire.py、funsport/api/flow.py、funsport/coordinates.py。字段诊断入口在funsport/diagnostics.py。

## 验证边界

点位显示已有使用者反馈恢复，不能推广为所有App版本、学校或模式均已验证。部分App地图桥接实现仍不透明；服务端有效性判定也不等同于客户端图标显示。

测试使用虚构点位与隔离目录，覆盖源顺序保留、缺省序号、异常顺序拒绝、重复提交保护，以及HTTP/OBS包装往返一致性。没有借助真实账号提交记录作为自动测试。

复现：python -m unittest -v tests.test_checkpoint_order tests.test_diagnostics tests.test_coordinates。

排查时只比较已有记录的App版本、policy、点位数量和position分布。不要分享密码、token、会话文件、原始抓包或带签名的对象地址，不要为验证重复上传旧记录。
