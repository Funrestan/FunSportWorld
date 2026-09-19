# 新增及改动函数说明

按本任务涉及模块的函数用途注释生成，包含测试辅助函数。未加用途注释的未改动历史函数不在本表中。

GUI 的 lambda 仅用作短回调；后台任务不直接读写 Tk 控件。

## funsport/gui.py

| 函数 | 作用 |
| --- | --- |
| configure_theme | 统一桌面配色、控件密度与焦点反馈，使用系统字体且不增加依赖。 |
| QueueLogHandler.__init__ | 保存 GUI 事件队列。 |
| QueueLogHandler.emit | 仅排队消息；实际脱敏和显示在主线程进行。 |
| App.__init__ | 创建窗口和各页，读取本地设置但不自动登录。 |
| App.page | 添加统一留白的页签。 |
| App.button | 建立可在任务运行时统一禁用的操作按钮。 |
| App.entry | 创建标签和输入框，并把值绑定到指定表单字典。 |
| App.build_run | 构建先预览后提交的表单、地图页及方案明细页。 |
| App.table | 创建有横纵滚动条的列表，长内容不会挤出窗口。 |
| App.build_records | 建立记录列表、单条记录查询和离线 JSON 诊断入口。 |
| App.build_tools | 提供原工具的策略、学期、排行榜和 AI 项目只读查询。 |
| App.build_settings | 建立凭据和校园位置表单；敏感输入默认遮挡且不自动回填。 |
| App.sync_modes | 按自动和时间模式禁用无效输入，避免界面与实际参数不一致。 |
| App.values | 在主线程复制表单值，后台任务不直接访问 Tk 变量。 |
| App.apply_snapshot | 刷新本地配置和会话提示，不展示密码或令牌。 |
| App.start_job | 串行执行任务，禁用重复提交并通过队列返回结果。 |
| App.start_job.work | 执行与 Tk 无关的工作，把结果或异常交回主线程。 |
| App.input_widgets | 遍历表单输入控件，以便任务进行时锁定当前参数。 |
| App.poll | 定时处理后台事件，恢复按钮并将异常显示为对话框。 |
| App.append_log | 脱敏后显示日志，并限制行数以免长时间使用占满内存。 |
| App.clear_log | 只清空界面日志，不删除任何本地数据文件。 |
| App.show_error | 显示脱敏错误，不输出原始堆栈或完整服务端响应。 |
| App.save_settings | 保存用户明确确认的设置，保存后清空敏感输入框。 |
| App.login | 仅在点击登录后调用现有登录链，不在后台自动尝试。 |
| App.login_done | 显示登录结果并清空临时密码，保留用户尚未保存的其他表单。 |
| App.logout | 确认后在后台请求服务器退出，成功回调前不清理会话或账号视图。 |
| App.logout_done | 服务器确认后清空预览，明确区分正常退出与本地文件清理失败。 |
| App.clear_account_views | 账号或校园变化后清空旧点位、记录、报告和查询结果。 |
| App.load_points | 在后台读取服务端点位或现有缓存。 |
| App.show_points | 把点位填入表格和图中，不把它们标记为已完成。 |
| App.draw_points | 按上传精度和已核实的App历史连线规则绘制轨迹、起终点及打卡点。 |
| App.add_tooltip | 为缩放符号提供简短的悬停说明。 |
| App.add_tooltip.leave | 离开按钮后销毁本按钮的提示窗口。 |
| App.add_tooltip.enter | 在按钮下方显示说明，不改变主窗口布局。 |
| App.fit_map | 把全部轨迹和打卡点放入视野，旧底图失效但不自动发请求。 |
| App.change_zoom | 改变地图缩放并清除旧底图，配置 Key 时重新加载。 |
| App.load_map | 请求当前视野的底图；不读表单密码、不发送轨迹。 |
| App.load_map.fetch | 后台获取图片，把底图失败当成可恢复的预览状态。 |
| App.map_loaded | 只使用与当前中心和缩放一致的图片，失败时保留轨迹。 |
| App.invalidate_plan | 参数或设置变化后废弃旧方案，避免提交与用户看到的参数不符。 |
| App.refresh_submit_state | 只有未使用的在线方案且没有后台任务时才允许确认提交。 |
| App.generate_preview | 校验表单后生成冻结方案，过程不提交运动记录。 |
| App.generate_route_preview | 使用手动参数、缓存点位和高德路线预览，不访问运动服务。 |
| App.show_plan | 展示已冻结的实际方案与各点最近采样距离，保留相同实例待提交。 |
| App.submit_run | 确认后只提交当前预览快照，时间外测试需要明确开启。 |
| App.run_done | 分别展示提交、OBS、详情读取和打卡字段状态，不混称全部成功。 |
| App.load_records | 后台查询当前账号的跑步记录列表。 |
| App.show_records | 按固定列显示记录，未知达标状态不显示成通过。 |
| App.select_record | 将所选记录的 ID 带入查询框，选择本身不发请求。 |
| App.diagnose_record | 查询用户指定的记录详情，并报告打卡字段是否可见。 |
| App.open_diagnostic | 让用户主动选择本地 JSON；不扫描数据目录、不上传文件。 |
| App.show_diagnostic | 显示只读诊断结果。 |
| App.set_report | 替换诊断区内容并回到顶部。 |
| App.set_text | 安全更新只读文本框。 |
| App.query_data | 执行下拉列表中选中的只读业务查询。 |
| App.query_data.query | 仅提取所需字段，避免把整个个人资料响应写入界面。 |
| App.close | 避免提交中途退出造成不明状态，关闭时恢复原日志处理器。 |
| launch | 启动桌面窗口；此函数本身不联网、不提交记录。 |

## funsport/gui_services.py

| 函数 | 作用 |
| --- | --- |
| read_object | 严格读取本地对象；文件损坏时拒绝以默认值覆盖原数据。 |
| number | 把表单文本转为有限数值，并验证范围和整数要求。 |
| settings_snapshot | 读取界面需要的配置；密码、地图 Key 和会话令牌不回填输入框。 |
| save_settings | 校验并合并设置；换账号前须退出服务器，避免丢弃仍有效的会话。 |
| login_account | 只为匹配账号使用保存密码；切换登录账号前须先完成服务器退出。 |
| with_client | 为单个后台任务创建独立客户端；无会话时不偷偷触发自动登录。 |
| logout_account | 用已有会话调用服务端退出并释放连接，不自动登录或降级为本地退出。 |
| run_parameters | 验证跑步表单，转换成方案生成参数，时间外测试默认关闭。 |
| fetch_record_report | 查询指定记录并只返回诊断统计，不把原始响应交给界面。 |
| safe_text | 删除日志中的常见凭据、手机号码和 URL 查询串。 |

## funsport/run_plan.py

| 函数 | 作用 |
| --- | --- |
| prepare_checkpoint_order | 仅为policy=1准备本次途经顺序；全缺失时从0编号，完整源顺序则排序，拒绝混合或冲突，不改通过状态。 |
| validate_checkpoint_plan | 校验各模式的预览与包装一致性，并拒绝旧顺序999方案，不改冻结数据。 |
| account_key | 用账号、学校和设备的摘要绑定方案，不在方案中保存登录令牌。 |
| RunPlan.create | 冻结完整轨迹、点位包装和策略参数，并拒绝 NaN。 |
| RunPlan.data | 获取独立副本；GUI 的展示处理不会改变内部快照。 |
| RunPlan.plan_id | 返回便于核对预览与提交一致性的内容摘要。 |
| RunPlan.attempted | 标识本方案是否已进入提交请求阶段，包括结果不明的失败。 |
| RunPlan.validate | 拒绝不可提交、过期、换账号、重复及顺序点位不一致的方案。 |
| RunPlan.claim | 在发请求前原子占用方案，防止重复或并发提交。 |
| checkpoint_distances | 计算轨迹采样点到打卡点的最近距离，仅作预览，不改写 isPass。 |
| format_plan | 展示冻结的时间、距离、点位顺序及道路指纹，不重新选路或生成。 |

## funsport/map_preview.py

| 函数 | 作用 |
| --- | --- |
| project | 将 GCJ-02 经纬度映射为对应缩放级别的墨卡托像素。 |
| unproject | 把地图像素中心转换回 GCJ-02 经纬度。 |
| fit_view | 选择能容纳轨迹和点位的中心与缩放，留出标记边距。 |
| screen_position | 计算与静态底图相同中心、缩放下的画布坐标。 |
| track_coordinates | 保留采样索引并采用上传的七位精度；None仅标无效样本，不决定连线。 |
| history_geometry | 按7.3.70可读历史地图规则抽样、着色及取起终点，不强制闭合。 |
| fetch_background | 请求受限大小的高德底图，不记录 Key、完整 URL 或响应正文。 |

## funsport/diagnostics.py

| 函数 | 作用 |
| --- | --- |
| decode_value | 解开有大小限制的 JSON 或 Base64+Gzip，兼容 OBS 字段编码。 |
| _valid_pair | 共用生成端的有限坐标和单轴占位校验，避免诊断结果不一致。 |
| analyze_checkpoints | 检查已知包装层，返回字段证据而非 App 的显示或达标结论。 |
| analyze_checkpoints.visit | 递归读取允许的字段，避免扫描或输出无关个人资料。 |
| format_report | 生成只含字段统计的中文报告，不回显账号、令牌和原始响应。 |
| inspect_file | 只读打开用户主动选择的 JSON 文件，并限制内存占用。 |

## funsport/main.py

| 函数 | 作用 |
| --- | --- |
| cmd_gui | 延迟导入 Tkinter，让有参数的 CLI 在无桌面环境下仍能运行。 |
| cmd_help | 显示已有命令摘要，不启动 GUI。 |
| main | 有参数时运行 CLI，无参数或 gui 子命令时打开桌面窗口。 |

## FunSportWorld.pyw

| 函数 | 作用 |
| --- | --- |
| main | 加载 GUI；缺失依赖时显示简洁提示，不输出配置或凭据。 |

## funsport/config.py

| 函数 | 作用 |
| --- | --- |
| _find_data_dir | 定位 .funsport 目录。 |
| save_json | 先完整写入同目录临时文件，再原子替换，避免配置只写了一半。 |
| get_amap_key | 优先级：环境变量 FUNSPORT_AMAP_KEY > config.json > 空。 |
| get_city | 优先级：config.json > identity.json > 默认。 |
| get_start_before_range | 返回 (min, max) 分钟。保证 min <= max，且都 >= 1。 |
| set_start_before | 设置提交时间提前量（分钟）。max 缺省 = min（固定）。 |
| clear_loop_cache | 删除环缓存（下次 --use-map 强制重新生成）。 |
| set_config | 批量更新配置项（只更新已存在的键）。 |
| load_points_cache | 兼容旧缓存读取，并按需返回点位、跑区信息和所属账号上下文。 |
| save_points_cache | 同时缓存点位和原始跑区信息，避免下一次序列化丢失元数据。 |

## funsport/api/client.py

| 函数 | 作用 |
| --- | --- |
| ApiClient.call | 发送现有协议请求；日志只记录元数据，不输出凭据或业务响应。 |

## funsport/api/errors.py

| 函数 | 作用 |
| --- | --- |
| BusinessError.__init__ | 记录业务码和去掉查询串的接口路径，并补充 11016 的操作边界。 |

## funsport/api/submit.py

| 函数 | 作用 |
| --- | --- |
| submit_record | 提交记录，并在业务拒绝时保留错误码和提交接口上下文。 |

## funsport/api/points.py

| 函数 | 作用 |
| --- | --- |
| fetch_points | 按参考 App 请求点位；按账号、校园和请求版本隔离缓存并保留包装字段。 |

## funsport/api/flow.py

| 函数 | 作用 |
| --- | --- |
| _ring_length | 用与现有生成器一致的距离单位估算规划环长度。 |
| _check_time_window | 检查 [start_ms, start_ms + dur*1000] 是否落在 valid_time 任一段内。 |
| _resolve_params | 统一解析最终 (dist_m, pace_s, cadence_spm)。 |
| _resolve_start_ms | 解析最终 start_ms。优先级：--before > 上游传入 > config 范围随机。 |
| _build_amap_track | 同一种子选择高德候选道路并生成轨迹，失败时不使用拟合环替代。 |
| prepare_run_plan | 查询后按模式确定点位顺序，用同一顺序规划和冻结数据，绝不提交。 |
| prepare_route_preview | 读取匹配账号的点位缓存，通过高德规划轨迹；不访问运动服务或提交。 |
| submit_run_plan | 提交已预览的同一快照；不再次随机生成、重查点位或重建路线。 |
| run_full_flow | 保留 CLI 一步执行入口，内部共用 GUI 的生成与提交阶段。 |

## funsport/track/wire.py

| 函数 | 作用 |
| --- | --- |
| gz | 按 OBS 字段约定压缩字节并编码为 Base64 字符串。 |
| gz_str | 将 UTF-8 文本编码成 OBS 使用的压缩字段。 |
| gz_json | 将对象序列化为紧凑 JSON 后压缩，不再嵌套额外引号。 |
| conv_point | 把生成器的 BD 采样转换成 App MyLocation 的 GCJ 坐标字段。 |
| five_point_payload | 保留源点位身份和状态，两套坐标统一到同一位置，不推断通过。 |
| five_point_wrapper | 保留接口提供的跑区和围栏，保持官方 PointJsonEntity 的双层结构。 |
| build_windows | 将十秒距离和步数窗口转换成 App 的速度及步频记录。 |
| build_laps | 按累计里程拆分每公里和末尾不足一公里的分段统计。 |
| build_obs_object | 组装 OBS；已有方案时复用提交的同一份点位包装。 |
| obs_keys | 按开始小时、UUID 和记录 ID 生成现有的两个 OBS 对象键。 |

## funsport/cli/cmds.py

| 函数 | 作用 |
| --- | --- |
| cmd_logout | 请求服务器退出并释放连接；失败保留会话并让 CLI 返回错误。 |
| cmd_run | 运行现有跑步链，并区分提交完成与详情、打卡点检查状态。 |

## funsport/api/records.py

| 函数 | 作用 |
| --- | --- |
| fetch_records | 读取记录摘要，保留服务端未提供达标状态时的未知值。 |
| fetch_one_record | 读取指定记录详情，并拒绝把空值或非对象误当成有效详情。 |

## tests/support.py

| 函数 | 作用 |
| --- | --- |
| IsolatedCase.setUp | 把全部配置路径替换为临时路径，测试结束自动还原。 |

## tests/plan_fixture.py

| 函数 | 作用 |
| --- | --- |
| sample_ring | 返回人工闭合折线，仅用作测试替身，不是实时高德返回数据。 |
| fake_client | 返回没有网络能力的示例账号客户端。 |
| sample_plan | 沿人工折线创建完整轨迹，仅在内存中组合方案快照。 |

## tests/test_diagnostics.py

| 函数 | 作用 |
| --- | --- |
| DiagnosticTests.test_coordinate_conflict_is_reported_without_locations | 双坐标冲突只展示米数和数量，不输出源位置或点名。 |
| DiagnosticTests.test_render_context_is_evidence_not_mode_override | 只记录原始数字模式字段，不推测或修改服务端运动类型。 |
| DiagnosticTests.test_conflicting_complete_is_unknown | 不同包装层的达标状态冲突时不能以后一个 True 覆盖 False。 |
| DiagnosticTests.test_current_wire_wrapper | 检查现有工具的双层 JSON，而不是误把包装对象当列表。 |
| DiagnosticTests.test_compressed_obs | 验证 OBS 的 Base64、Gzip、JSON 三层解码。 |
| DiagnosticTests.test_complete_is_not_checkpoints | 服务端 complete=true 不能被诊断为存在打卡点。 |
| DiagnosticTests.test_empty_and_corrupt_are_distinct | 区分缺字段、空列表和无法解析的字段。 |
| DiagnosticTests.test_invalid_coordinates | 拒绝空值、无穷值、越界和字符串布尔值作为有效坐标或通过状态。 |
| DiagnosticTests.test_read_only_and_private | 诊断不修改输入，也不输出令牌、姓名或原始点名。 |
| DiagnosticTests.test_compressed_size_limit | 限制解压体积，避免小压缩文件消耗大量内存。 |
| DiagnosticTests.test_nested_limit | 过深包装返回明确解析警告。 |
| DiagnosticTests.test_utf8_bom_file | 用户选择的 UTF-8 BOM 文件可以离线诊断。 |
| DiagnosticTests.test_file_limit | 超过文件大小限制时停止解析。 |

## tests/test_gui_services.py

| 函数 | 作用 |
| --- | --- |
| ServiceTests.test_clear_coordinates_invalidates_cache | 清空坐标也清空校园缓存，不回填被用户删除的旧坐标。 |
| ServiceTests.test_captcha_fields_are_redacted | 失败消息中的验证码凭据同样脱敏。 |
| ServiceTests.form | 构造一个有效的设置表单供测试修改。 |
| ServiceTests.test_preserve_unknown_settings_and_password | 保留未知字段、既有设备身份和同账号未改动的密码。 |
| ServiceTests.test_forget_password | 取消记住密码时真正清除本地密码，不只改变复选框。 |
| ServiceTests.test_account_change_after_logout_clears_cache | 已经退出后切换账号清除旧学校点位与旧密码，避免跨账号复用。 |
| ServiceTests.test_account_change_requires_server_logout_before_writes | 存在旧会话时禁止切换设置，所有配置与缓存均不变。 |
| ServiceTests.test_saving_current_session_account_is_not_switching | 先登录后首次保存同账号设置不要求退出，也不删除现有会话。 |
| ServiceTests.test_corrupt_config_is_not_overwritten | 配置损坏时拒绝覆盖，并保证原始字节不变。 |
| ServiceTests.test_invalid_form_does_not_write | 所有字段校验都应在写盘之前完成。 |
| ServiceTests.test_atomic_write_failure_preserves_original | 原子替换失败时保留原文件并清理临时文件。 |
| ServiceTests.test_invalid_number | 数字输入拒绝 NaN、无穷、越界和小数整数值。 |
| ServiceTests.test_run_parameters | 手动字段与自动字段分离，只有所选时间模式产生参数。 |
| ServiceTests.test_start_time | 指定时间只接受过去三天内的正确日期格式。 |
| ServiceTests.test_missing_session_does_not_login | 只读按钮在无会话时提示登录，不自动触发验证码流程。 |
| ServiceTests.test_client_closes_after_failure | 业务失败时也释放 HTTP 会话。 |
| ServiceTests.test_snapshot_does_not_expose_secrets | 状态快照仅返回是否配置，不返回密码、地图 Key 或令牌。 |
| ServiceTests.test_log_redaction | 日志遮蔽显式秘密、手机号、JSON 令牌和签名 URL 查询串。 |
| ServiceTests.test_main_entrypoints | 无参数和 gui 启动窗口，help 保持命令行输出。 |

## tests/test_flow_status.py

| 函数 | 作用 |
| --- | --- |
| FlowTests.run_fake_flow | 替换每个外部边界，保留实际编排和诊断代码。 |
| FlowTests.test_returned_record_is_not_passed_record | 记录能读到但 complete=false 时，不能被报告为跑步达标。 |
| FlowTests.test_partial_obs_remains_partial | 即使详情能读取，也保留 OBS 部分上传的状态。 |
| FlowTests.test_detail_failure_keeps_submission_id | 详情失败仍返回已提交的记录 ID，避免引导用户重复提交。 |
| FlowTests.test_detail_rejects_list | 非对象详情不能算读取验证成功。 |
| FlowTests.test_records_preserve_unknown_complete | 服务端没给 complete 时，列表保留未知而不是强行判否。 |

## tests/test_gui.py

| 函数 | 作用 |
| --- | --- |
| GuiTests.test_account_change_clears_all_views | 保存新账号或校园配置后，不保留上一个账号的详情和查询结果。 |
| GuiTests.setUp | 建立隔离窗口并将系统消息框替换为测试替身。 |
| GuiTests.cleanup_window | 测试后终止本测试自己的 Tk 窗口并恢复日志处理器。 |
| GuiTests.pump | 推进 Tk 事件循环直到后台任务和队列都结束。 |
| GuiTests.test_startup_does_not_write_or_login | 启动只读配置，不创建身份、不保存配置、更不联网。 |
| GuiTests.test_logout_cancel_never_requests | 用户取消退出确认时不发送请求、不删除本地会话。 |
| GuiTests.test_logout_waits_for_server_and_clears_preview | 后台请求完成前保留会话；服务器成功后才清空界面和密码输入。 |
| GuiTests.test_logout_waits_for_server_and_clears_preview.request | 阻塞假服务器响应以检查进行中状态，随后返回成功码。 |
| GuiTests.test_logout_failure_preserves_account_view | 失败后恢复按钮但不清空当前方案，也不显示未登录。 |
| GuiTests.test_logout_local_cleanup_failure_shows_partial_state | 服务器已退出但文件删除失败时，界面明确报告部分成功。 |
| GuiTests.test_mode_controls | 自动模式禁用手动参数，时间模式只启用对应输入。 |
| GuiTests.test_invalid_form_never_submits | 表单非法时不执行任何后台请求。 |
| GuiTests.test_declined_confirmation_never_submits | 用户取消确认时不发送请求。 |
| GuiTests.test_submission_displays_partial_status | 提交一次后显示结果与部分上传状态，不显示打卡已验证。 |
| GuiTests.test_only_one_background_job | 首个任务未完成时，第二次点击不会产生第二个任务。 |
| GuiTests.test_generate_does_not_submit | 生成预览只执行准备阶段，提交按钮随后才启用。 |
| GuiTests.test_parameter_changes_invalidate_preview | 修改任何轨迹参数后旧方案失效，不能提交旧预览。 |
| GuiTests.test_summary_uses_frozen_plan_values | 概览显示最终方案而非表单目标；换账号后不保留旧点位指标。 |
| GuiTests.test_outside_toggle_keeps_same_preview | 时间外开关只改变提交许可，不重新生成已检查的轨迹。 |
| GuiTests.test_map_failure_preserves_preview | 底图请求失败不丢失轨迹和可检查的方案。 |
| GuiTests.test_local_preview_never_autoloads_map_or_enables_submit | 本地预览不自动加载底图；按钮与后端都不能把它当成在线方案。 |
| GuiTests.test_error_restores_controls_and_redacts | 任务异常后恢复交互，且对话框和日志不含输入的密码。 |
| GuiTests.test_record_selection_and_unknown_status | 记录选择仅填 ID，未返回的达标状态显示未知。 |
| GuiTests.test_close_while_busy_is_blocked | 提交中不直接退出，避免用户无法判断记录是否已经写入。 |

## tests/test_run_plan.py

| 函数 | 作用 |
| --- | --- |
| PlanTests.submission_mocks | 模拟提交、OBS 与详情边界，保留中间序列化逻辑。 |
| PlanTests.test_exact_track_and_wrapper_submitted | 提交轨迹等于快照，HTTP 和 OBS 的打卡包装内容完全一致。 |
| PlanTests.test_preview_copy_cannot_mutate_submission | 修改读出的字典不会改变内部快照或方案 ID。 |
| PlanTests.test_generation_never_submits | 准备阶段只读取和生成，即使处于有效时间外也可以查看。 |
| PlanTests.test_outside_requires_explicit_override | 窗口外默认不发请求，明确开启后可进入测试提交。 |
| PlanTests.test_unknown_network_result_cannot_retry_same_plan | 请求超时后的方案也锁定，防止实际已提交但再次写入。 |
| PlanTests.test_owner_expiry_and_future_checks | 不接受别的账号、过期方案，也不把时间外开关当成未来记录开关。 |
| PlanTests.test_full_interval_and_overnight_windows | 跨午夜必须包含整个区间；支持合法的跨午夜开放时段。 |
| PlanTests.test_final_generated_duration_controls_window | 原参数在窗口内但实际轨迹超时，应按最终轨迹显示窗口外。 |
| PlanTests.test_wire_preserves_metadata_without_faking_pass | 保留服务器点位信息，不把所有点统一标记为通过。 |
| PlanTests.test_invalid_coordinates_are_rejected | 只有占位、布尔或非有限坐标时不能悄悄生成在零点的方案。 |
| PlanTests.test_partial_gcj_sentinel_falls_back | 单个高德坐标为默认值时，预览也像参考 App 一样回退百度坐标。 |

## tests/test_point_metadata.py

| 函数 | 作用 |
| --- | --- |
| PointTests.client | 提供可记录调用次数的离线点位客户端。 |
| PointTests.test_metadata_survives_network_and_cache | 接口和缓存两条路径都保留跑区和围栏信息。 |
| PointTests.test_point_request_does_not_force_sport_type | 点位请求按参考客户端不带 sportType，不能强行请求自由跑类型。 |
| PointTests.test_old_request_cache_is_not_reused_or_fallback | 旧请求版本缓存不进入在线方案，请求失败也不能回退该缓存。 |
| PointTests.test_account_change_does_not_reuse_cached_points | 账号或学校变化时旧缓存不参与新的点位请求。 |
| PointTests.test_fresh_failure_does_not_fall_back | 准备新方案时请求失败必须报错，不能静默使用缓存替代。 |
| PointTests.test_preview_uses_fresh_cache_but_rejects_stale_fallback | 反复预览可复用有效缓存，缓存过期后网络失败不能降级。 |

## tests/test_map_preview.py

| 函数 | 作用 |
| --- | --- |
| MapTests.test_projection_round_trip | 像素投影及其逆变换保持坐标。 |
| MapTests.test_fit_keeps_all_points_visible | 适配后所有样本点落入指定画布内部。 |
| MapTests.test_track_conversion_and_invalid_gaps | 轨迹转换到高德坐标，定位无效点保留断线标志。 |
| MapTests.response | 构造支持流式读取和上下文管理的离线 HTTP 响应。 |
| MapTests.test_background_requests_only_center | 底图请求不包含轨迹、点位数组和运动账号信息。 |
| MapTests.test_no_key_does_not_request | 没有配置 Key 时只返回可操作提示，不发送无效请求。 |
| MapTests.test_error_does_not_expose_key | 网络异常中即使带 Key，也只向上返回固定安全提示。 |
| MapTests.test_json_error_and_wrong_size | JSON 错误响应和尺寸错误都不能被当成底图叠加。 |

## tests/test_server_time_error.py

| 函数 | 作用 |
| --- | --- |
| ServerTimeTests.test_business_error_keeps_safe_context | 显示接口与失败阶段，但不暴露 URL 查询串中的令牌。 |
| ServerTimeTests.test_other_errors_do_not_get_time_diagnosis | 其他业务错误仍保留原含义，不误套时间限制说明。 |
| ServerTimeTests.test_client_raises_structured_policy_error | 通用客户端把假服务端 11016 转成带接口的结构化异常。 |
| ServerTimeTests.test_outside_flag_does_not_swallow_policy_rejection | 策略阶段被拒绝后，开关即使开启，也不能继续获取点位或提交。 |
| ServerTimeTests.test_submit_error_reports_submission_stage | 直接提交接口的 11016 也标明提交阶段，而非误称仍在生成预览。 |
| LocalPreviewTests.cache_points | 保存一个匹配示例账号、但故意过期的缓存。 |
| LocalPreviewTests.test_route_preview_calls_no_sports_operation | 轨迹预览使用高德路线，但不调用运动策略、点位、提交或 OBS。 |
| LocalPreviewTests.test_local_preview_cannot_submit_even_with_override | 即使调用后端并显式跳过时间检查，本地测试轨迹也不能提交。 |
| LocalPreviewTests.test_local_preview_requires_matching_cache | 不使用空缓存、别的账号缓存或无法证明归属的旧格式缓存。 |

## tests/gui_smoke.py

| 函数 | 作用 |
| --- | --- |
| visible_widgets | 递归收集当前页可见控件，用于检查是否超出窗口。 |
| main | 使用完整离线方案渲染地图和明细，检查像素与控件边界。 |

## funsport/coordinates.py

| 函数 | 作用 |
| --- | --- |
| coordinate_pair | 读取有限坐标，拒绝布尔、越界和 App 常见的单轴占位值。 |
| gcj02_to_bd09 | 将 GCJ-02 转为 BD-09，全精度计算，仅在输出 JSON 时取舍小数。 |
| bd09_to_gcj02 | 先近似反算，再迭代消除正反转换残差；不宣称改善原始定位精度。 |
| distance_m | 计算同坐标系两点的球面距离，返回米。 |
| checkpoint_coordinates | 以有效原生高德坐标为准统一两套坐标；缺失时才从百度推算。 |
| coordinate_report | 只返回坐标来源及双坐标差异统计，不泄露原始经纬度。 |

## funsport/api/campus_loop.py

| 函数 | 作用 |
| --- | --- |
| dist_m | 计算同一坐标系中两点的球面距离，用于分段和端点检查。 |
| turn_angle_deg | 计算相邻折线段的转角，供原始折线的细分使用。 |
| _amap_walking | 一次请求最多三条高德候选；默认仍返回首条，错误不包含Key。 |
| _step_polylines | 逐个提取嵌套步骤，保留步骤边界以检查每一处接缝。 |
| _parse_amap | 解析指定候选的完整polyline，坏坐标或断线不会污染其他候选。 |
| _dedup_exact | 仅删除相邻重复顶点，不改变路线顺序。 |
| _dedup_min_dist | 移除过密顶点，同时保留原有路线走向。 |
| _densify_turns | 沿现有线段补中点，不使用曲线拟合重新规划道路。 |
| _sanitize | 对高德折线做去重和线段细分。 |
| _points_fingerprint | 指纹包含点位顺序；同一组点改顺序也必须重新规划。 |
| _ring_digest | 校验缓存折线的完整内容和顺序，检测意外损坏而非认证高德签名。 |
| _validate_leg_option | 统一检查网络或缓存的单段道路坐标、里程、来源及端点。 |
| _fetch_route_legs | 按固定点位顺序请求各段候选；每段只发一次正常v5请求。 |
| _options_digest | 计算分段候选的规范内容摘要，防止读取被意外改动的缓存。 |
| _validated_legs | 校验候选缓存的段数、每段上限和所有道路，不接受部分损坏缓存。 |
| _assemble_loop | 拼接所选的真实道路；接缝或闭合失败时拒绝，不跨区域补直线。 |
| _select_loop | 由种子确定分段道路组合，跳过断线组合，保持选择可复现。 |
| build_loop | 请求候选并选择一条闭环，保留直接调用者的BD折线返回格式。 |
| _validated_ring | 校验路线有限坐标、闭合和点位覆盖；无效缓存不得进入生成器。 |
| get_campus_loop | 从完整候选缓存按种子选路，不把整个闭环固定成同一道路。 |

## tests/test_coordinates.py

| 函数 | 作用 |
| --- | --- |
| CoordinateTests.test_round_trip_grid | 多纬度多经度的正反转换数值残差小于一厘米。 |
| CoordinateTests.test_native_gcj_wins_over_conflicting_bd | 两套源坐标冲突时统一到原生高德位置，并保留差异统计。 |
| CoordinateTests.test_bd_only_preserves_source_and_is_idempotent | 百度源点只转换一次，重复序列化不持续漂移。 |
| CoordinateTests.test_partial_sentinels_rejected | 空轴、布尔、非数字和非有限坐标不能进入规划。 |
| CoordinateTests.test_preview_uses_same_conversion_as_wire | 同一轨迹点的上传与地图预览坐标在七位小数内一致。 |

## tests/test_campus_loop.py

| 函数 | 作用 |
| --- | --- |
| CampusLoopTests.source | 返回有意制造双坐标冲突的源点及其规范化 BD 闭环。 |
| CampusLoopTests.payload | 组合高德 v3/v5 共用的步行路径包装。 |
| CampusLoopTests.response | 创建带资源关闭语义的 HTTP 模拟响应。 |
| CampusLoopTests.legs | 返回每段一条人工候选道路，保持现有缓存测试的固定几何。 |
| CampusLoopTests.test_parse_steps_and_nested_gaps | 保留合法折线，嵌套步骤也逐段校验接缝。 |
| CampusLoopTests.test_bad_response_never_produces_partial_route | 坏坐标和错误结构不会留下可继续生成的半条路线。 |
| CampusLoopTests.test_v3_fallback_closes_both_responses | v5 无数据时允许 v3，两个响应都关闭且请求经度在前。 |
| CampusLoopTests.test_amap_failure_does_not_expose_key | 网络错误即使包含 Key，也只能向用户返回固定安全消息。 |
| CampusLoopTests.test_cache_and_native_gcj_inputs | 规划直接接收原生 GCJ，第二次命中已校验路线且不读取 Key。 |
| CampusLoopTests.test_bad_cache_requires_rebuild | 版本、来源、顺序、过期、未来时间和坏路径都会让缓存失效。 |
| CampusLoopTests.test_invalid_points_rejected_before_key_or_network | 不跳过无坐标点位，也不请求非法经纬度。 |
| CampusLoopTests.test_single_polyline_teleport_rejected | 单条 polyline 内的跨城市跳点不能以端点正常为由被接受。 |
| CampusLoopTests.test_json_decode_failure_closes_response | 响应正文不是 JSON 时关闭资源并尝试另一个高德版本。 |
| CampusLoopTests.test_full_gcj_route_preview_and_wire_chain | 仅替换 HTTP，核对每段请求及返回路线的预览和上传坐标一致。 |
| CampusLoopTests.test_missing_key_or_route_failure_never_builds_track | 缺 Key 或路线接口失败时直接停止，不降级为数学拟合轨迹。 |
| CampusLoopTests.test_segment_endpoints_and_closure | 环必须通过各请求端点并连续闭合，不补长直线修复断路。 |

## funsport/api/login.py

| 函数 | 作用 |
| --- | --- |
| _geevalidate | 直接走 envelope_request，返回 error 码，不抛异常。 |
| logout | 使用当前会话请求服务器退出；确认成功才清理本地，失败保留凭据。 |

## tests/test_logout.py

| 函数 | 作用 |
| --- | --- |
| LogoutTests.setUp | 在临时目录保存示例会话，所有客户端请求都由 Mock 替代。 |
| LogoutTests.test_request_precedes_local_cleanup | 请求过程中本地凭据仍存在，收到成功后才清除文件和内存会话。 |
| LogoutTests.test_request_precedes_local_cleanup.successful_request | 在假服务器返回前核对退出使用的仍是原账号会话。 |
| LogoutTests.test_logout_transport_uses_existing_uid_and_token | 保留真实客户端调用链，仅模拟加密和 HTTP，确认原会话用于认证。 |
| LogoutTests.test_rejected_logout_keeps_session | 业务拒绝不会清除会话或返回成功，并保留错误码。 |
| LogoutTests.test_timeout_keeps_session_and_reports_unknown | 网络超时不推断服务器状态、不自动重试，也不暴露底层秘密。 |
| LogoutTests.test_unconfirmed_response_keeps_session | 空响应、异常结构及非成功码不能被误报为退出成功。 |
| LogoutTests.test_missing_credentials_never_clears_or_requests | 认证字段不完整时无法远程退出，不能仅删除本地文件。 |
| LogoutTests.test_server_success_local_failure_is_distinct | 磁盘删除失败单独报告：服务器已退出但本地文件仍保留。 |
| LogoutTests.test_gui_service_closes_connection_success_and_failure | 适配层调用真实退出函数，成功或失败都关闭 HTTP 会话。 |
| LogoutTests.test_cli_calls_shared_logout_and_closes_connection | 命令行同样等待服务器确认，失败会向上传递错误。 |
| LogoutTests.test_cli_failure_returns_nonzero | CLI 退出失败的进程状态不是成功，日志不含底层请求秘密。 |
| LogoutTests.test_cli_local_cleanup_failure_closes_connection_and_fails | CLI 服务器已退出但本地清理失败时，仍释放连接且不返回正常完成。 |
| LogoutTests.test_cli_missing_session_does_not_create_identity | 无会话的 CLI 退出不创建新设备身份，也不尝试远程请求。 |
| LogoutTests.test_gui_service_without_session_never_logs_in | 已无会话时不能为了退出而自动创建身份、登录或发送请求。 |
| LogoutTests.test_new_account_login_preserves_old_session | 未退出旧账号时，不允许通过登录新账号覆盖退出所需凭据。 |

## tests/test_checkpoint_order.py

| 函数 | 作用 |
| --- | --- |
| CheckpointOrderTests.points | 创建四个带稳定身份和不同通过状态的虚构点位。 |
| CheckpointOrderTests.ring_for_points | 按传入顺序组成离线折线，并兼容带选路信息的新返回格式。 |
| CheckpointOrderTests.prepare | 模拟策略和路线边界，执行真实的规划与序列化函数。 |
| CheckpointOrderTests.submission_mocks | 替换所有提交网络边界，保留HTTP参数和OBS内容供检查。 |
| CheckpointOrderTests.assert_rejected_before_submit | 错误方案必须在网络请求和单次提交门闩之前被拒绝。 |
| CheckpointOrderTests.test_missing_sequence_follows_route_without_mutating_source | 只在复制的规划点位上补零起始编号，身份和通过状态原样保留。 |
| CheckpointOrderTests.test_all_sentinels_and_nulls_are_missing_sequence | 整组只有缺省、null或整数999时，采用同一个规划顺序。 |
| CheckpointOrderTests.test_complete_source_order_is_sorted_not_renumbered | 保留已有编号的点位身份，按源编号重排实际途经列表。 |
| CheckpointOrderTests.test_nonsequential_policies_preserve_input | policy为0、2、3和旧版-1时不编号、不排序、不改字段。 |
| CheckpointOrderTests.test_partial_sequence_is_not_guessed | 已有编号和缺失编号混杂时失败，不覆盖有意义的源顺序。 |
| CheckpointOrderTests.test_malformed_sequences_are_rejected | 拒绝重复、跳号、一基编号、负数及伪装整数的布尔或文本。 |
| CheckpointOrderTests.test_point_count_matches_app_icon_bounds | 五个编号可用，空列表和六个点不会造成App数组越界。 |
| CheckpointOrderTests.test_unknown_policy_is_not_treated_as_sequence | 不把True、浮点数或字符串1当成已确认的整数策略。 |
| CheckpointOrderTests.test_generation_assigns_same_order_to_route_preview_and_wrapper | 真实准备流程把相同编号交给路线规划、预览及HTTP包装。 |
| CheckpointOrderTests.test_generation_routes_by_existing_order | 源顺序打乱时，传给高德的列表也同步排序，不只修改上传JSON。 |
| CheckpointOrderTests.test_generation_for_other_policy_keeps_999 | 完整准备流程在其他策略下维持原行为，不扩大修复范围。 |
| CheckpointOrderTests.test_invalid_order_stops_before_route_request | 有歧义的顺序在高德路线请求之前停止，也不调用提交。 |
| CheckpointOrderTests.test_submission_keeps_repaired_wrapper_and_pass_states | 从缺省顺序生成后，HTTP和解压OBS均保持编号与原通过状态。 |
| CheckpointOrderTests.test_old_999_plan_requires_new_preview | 已冻结的旧999方案不能在提交时静默修复，时间外开关也不豁免。 |
| CheckpointOrderTests.test_unsorted_frozen_plan_requires_new_preview | 即使编号存在，冻结列表与规划顺序不一致也必须重新预览。 |
| CheckpointOrderTests.test_wrapper_mismatch_is_rejected | HTTP包装中的顺序、通过状态或身份不能偏离已预览点位。 |
| CheckpointOrderTests.test_malformed_wrapper_is_rejected | 损坏JSON、裸数组或不支持的压缩标记不能通过提交前检查。 |
| CheckpointOrderTests.test_other_policies_also_validate_preview_wrapper | 非顺序策略仍检查预览与包装一致，但不改变999或源顺序。 |

## funsport/track/generator.py 与 postfix.py

| 函数 | 作用 |
| --- | --- |
| fit_speeds | 在速度上下限内迭代匹配目标里程，原地更新每段速度。 |
| _make_dips | 生成速度曲线的缓慢降速区间，不代表App暂停事件。 |
| _dip_factor | 计算指定时刻在平滑降速区间中的速度倍率。 |
| build | 沿路径生成轨迹；有序规划不随机伪造无效、越界或打卡点类型，保证里程与起终点一致。 |
| apply_post_fixes | 有序规划只标终点；旧拟合模式保留原后处理，不伪造规划段的事件。 |

## tests/test_route_geometry.py

| 函数 | 作用 |
| --- | --- |
| RouteGeometryTests.build | 沿固定闭环生成已知里程的有序测试轨迹。 |
| RouteGeometryTests.typed_track | 创建便于人工核对抽样索引的少量轨迹点。 |
| RouteGeometryTests.test_thirty_seeds_complete_requested_lap | 此前19次不足一圈的30个种子，现在均达到目标且不伪造业务事件。 |
| RouteGeometryTests.test_one_lap_returns_to_start_on_the_path | 目标为一整圈时真实上传采样首尾相接，不只在画布上补线。 |
| RouteGeometryTests.test_partial_extra_lap_does_not_teleport_to_start | 一圈加部分里程可覆盖闭环，但不强行把终点改回起点。 |
| RouteGeometryTests.test_start_time_distance_and_identifiers_are_consistent | 起点为t=0，后续时间与里程递增，终点数据和轨迹汇总相同。 |
| RouteGeometryTests.test_infeasible_speed_does_not_make_terminal_jump | 无法在速度约束内覆盖里程时失败，不用最后一点瞬移凑距离。 |
| RouteGeometryTests.test_invalid_samples_are_skipped_not_line_breaks | 起终点之间的type=-1像App一样跳过，不导致整段线消失。 |
| RouteGeometryTests.test_same_type_and_heading_retains_every_other_point | 同类型且方向差不超过10度时，对照APK保留第0、2、4点。 |
| RouteGeometryTests.test_type_and_heading_changes_preserve_points | 类型变化或方向差超过10度会保留点，边界10度本身不会触发。 |
| RouteGeometryTests.test_app_colors_and_explicit_markers | 起终点来自type5/6，灰色和红色业务点不再全部画成蓝线。 |
| RouteGeometryTests.test_preview_coordinates_equal_decoded_obs | 预览逐点使用与实际OBS解压后完全相同的七位GCJ坐标。 |
| RouteGeometryTests.test_empty_track_has_no_invented_line_or_markers | 无有效点时没有轨迹或起终点，不补造位置。 |
| RouteGeometryTests.test_endpoint_matches_arc_progress_after_snapping | 逐点吸附完成后，终点仍由真实弧长重算，不被附近顶点覆盖。 |
| RouteGeometryTests.test_distance_windows_use_corrected_progress | 制造0.75m拟合残差，窗口里程仍跟随校正后的实际累计值。 |
| RouteGeometryTests.test_distance_windows_use_corrected_progress.undershoot | 只在测试中制造允许范围内的拟合偏差，检验末段校正。 |
| RouteGeometryTests.test_one_second_tail_is_not_dropped_or_extrapolated | 不足十秒的最后一秒保留真实里程和时长，不扩大成十秒。 |

## tests/test_route_options.py

| 函数 | 作用 |
| --- | --- |
| RoadOptionTests.points | 提供固定顺序、固定身份和未通过状态的四个虚构点位。 |
| RoadOptionTests.legs | 每段提供几何不同的人工道路，代表高德返回的备选而非真实查询。 |
| RoadOptionTests.payload | 把人工候选转换成高德JSON返回格式。 |
| RoadOptionTests.response | 创建会关闭资源的HTTP响应替身。 |
| RoadOptionTests.warm_cache | 只在隔离临时目录中建立候选缓存，不访问用户目录。 |
| RoadOptionTests.prepare_plan | 保留真实选路和轨迹生成，仅替换运动服务读取边界。 |
| RoadOptionTests.test_single_request_returns_up_to_three_options | 一次v5请求启用alternative_route=3，读取三条而不发三次请求。 |
| RoadOptionTests.test_invalid_and_duplicate_options_do_not_count | 坏的首条和重复路线不掩盖有效备选，也不虚报道路数量。 |
| RoadOptionTests.test_seed_changes_roads_without_network_or_cache_rewrite | 缓存完整候选后，种子0/1/2产生不同道路，而相同种子复现。 |
| RoadOptionTests.test_single_road_is_reported_without_faking_variation | 每段只有一条时坦诚返回同一道路，不按种子画假岔路。 |
| RoadOptionTests.test_broken_join_skips_combo_instead_of_drawing_connector | 候选端点相差超过3米时尝试另一组合，不新增跨接直线。 |
| RoadOptionTests.test_all_broken_combos_preserve_previous_cache | 所有组合断线时生成失败，不覆盖之前有效的候选缓存。 |
| RoadOptionTests.test_old_single_loop_cache_requires_successful_refresh | 旧schema3不再锁定道路，更新失败时保留旧文件但不冒充新候选。 |
| RoadOptionTests.test_candidate_tampering_requires_refresh | 即使改的是本次未选中的候选，也必须通过全内容摘要校验。 |
| RoadOptionTests.test_candidate_limits_and_coordinates_are_validated | 缓存中的空段、超量候选、布尔坐标和重复道路全部拒绝。 |
| RoadOptionTests.test_invalid_seed_does_not_request_or_replace_cache | 非整数道路种子在读取Key或请求之前被拒绝。 |
| RoadOptionTests.test_plan_seeds_choose_different_roads_keep_checkpoint_order | 端到端准备方案改变道路，但不改学校顺序、身份、状态和包装。 |
| RoadOptionTests.test_auto_seed_is_fresh_even_when_clock_does_not_advance | 自动种子不再靠毫秒时间，不会因相同时间戳固定选路。 |
| RoadOptionTests.test_route_preview_uses_seed_but_remains_unsubmittable | 仅轨迹预览也可换道路，但没有学校策略时仍不能提交。 |
| RoadOptionTests.test_first_response_and_cached_selection_match | 同一种子直接解析HTTP响应与随后读取候选缓存选出的道路一致。 |
| RoadOptionTests.test_five_point_three_option_space_reaches_last_combo | 五点三候选的第243种组合仍能被准确选择，没有边界漏选。 |
| RoadOptionTests.test_incompatible_combo_search_is_bounded | 超过512种且全部不连通时有界失败，不无限枚举或补线。 |
| RoadOptionTests.test_exact_twenty_four_hour_cache_is_expired | 达到24小时边界即刷新，不因换种子或读取缓存延长有效期。 |
