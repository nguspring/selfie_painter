# selfie_painter_v2 代码审查修复记录

**修复时间**：2026-07-21  
**审查基线**：commit 24e434e  
**修复范围**：F1-F20（共20个问题）

---

## 已修复问题清单

### P0 - 阻断级（2项）

#### ✅ F1 【阻断】插件启用时在组件装配阶段崩溃
**文件**：`core/lifecycle_handler.py`

**修复内容**：
1. `EventHandlerInfo` 参数从 `component_name=` 改为 `name=`（行40、80）
2. 方法名从 `handle()` 改为 `execute()`（行46、86）
3. 返回值从二元组改为五元组 `(bool, bool, str|None, Any, MaiMessages)`
4. 移除 `self.plugin` 访问，改用 `plugin_manager.loaded_plugins.get(self.plugin_name)` 从注册表获取实例
5. 移除 `CustomEventHandlerResult.CONTINUE`，改用返回值中的 `continue_processing=True`

**验证**：compileall 通过，ruff 通过

---

#### ✅ F2 【高危·安全】配置目录含疑似真实明文 API Token
**文件**：`config.toml:345,417,444,471,498,525`

**状态**：已识别位置，需用户手动处理
- 6 处 `api_key` 赋值去重后仅 1 个唯一值（`Bearer ` 开头 len=46）
- 备份文件已从 23 个清理到 0 个
- **待用户操作**：确认是否为真实密钥，若是则立即撤销并轮换，将配置文件中的值替换为占位符

---

### P1 - 高危（2项）

#### ✅ F3 【高危】日程 Prompt 注入不会被宿主采用
**文件**：`core/schedule_inject_handler.py:159`

**修复内容**：
- 在修改 `message.llm_prompt` 后添加 `message.modify_llm_prompt(message.llm_prompt)` 调用
- 移除无效的 `host_modified` 检查分支

**验证**：语法检查通过

---

#### ✅ F4 【高危】不存在的模型 ID 可绕过受限默认模型权限
**文件**：
- `core/utils/model_utils.py:get_model_config()`
- `core/pic_action.py:264,282,_get_model_config()`
- `core/pic_command.py:372,_get_model_config()`

**修复内容**：
1. `get_model_config()` 返回值从 `Optional[Dict]` 改为 `tuple[str, Optional[Dict]]`，返回 `(实际配置节ID, 配置字典)`
2. 回退到默认模型时返回 `(default_model_id, config)` 而非 `(model_id, config)`
3. Action 和 Command 中所有 `_get_model_config()` 调用改为解包：`actual_model_id, model_config = self._get_model_config(...)`
4. 权限检查使用 `actual_model_id` 而非请求的 `model_id`

**验证**：compileall 通过，ruff 通过

---

### P2 - 中危（8项）

#### ✅ F5 【中危】自动自拍历史聊天流预加载固定失败
**文件**：`core/selfie/auto_selfie_task.py:520`

**修复内容**：
- 导入路径从 `src.chat.chat_stream` 改为 `src.chat.message_receive.chat_stream`

**验证**：语法检查通过

---

#### ✅ F6 【中危】热卸载和热重载不会清理插件后台任务
**文件**：`core/lifecycle_handler.py`

**修复内容**：
- 修复 F1 后，`LifecycleStopHandler` 可正常注册并在 `ON_STOP` 事件时调用 `plugin.on_plugin_unload()`
- 从注册表获取插件实例并调用清理方法

**验证**：语法检查通过

**注意**：完整修复需宿主在热卸载/重载时派发 `ON_STOP` 事件，或在 `PluginManager.remove_registered_plugin()` 中直接调用 `on_plugin_unload()`

---

#### ✅ F7 【中危】ScheduleDB 线程本地连接会跨数据库实例串用
**文件**：`core/schedule/schedule_db.py:26,60-73`

**修复内容**：
1. `_thread_local.conn` 改为 `_thread_local.conns: dict[str, Connection]`
2. `_get_conn()` 方法按 `self.db_path` 区分缓存连接
3. 新增 `close_all_connections()` 类方法，用于插件卸载时关闭所有连接

**验证**：语法检查通过

---

#### ✅ F8 【中危】SQLite 迁移只相信版本号，不核对真实列结构
**文件**：`core/schedule/schedule_db.py:136-165`

**修复内容**：
- 将版本号检查移到列检查之后
- 改为"版本≥2 **且** outfit 列存在"时才跳过迁移
- 若版本=2 但列不存在，仍执行 ALTER TABLE 添加列

**验证**：语法检查通过

---

#### ✅ F9 【中危】ensure_today_schedule 会重复创建未跟踪的 LLM 覆盖任务
**文件**：`core/schedule/schedule_manager.py:38,49-76`

**修复内容**：
1. `ScheduleManager.__init__()` 中添加 `self._llm_override_tasks: dict[str, asyncio.Task] = {}`
2. `ensure_today_schedule()` 中检查 `today` 是否已有未完成的任务，有则跳过
3. 创建新任务后保存句柄到 `_llm_override_tasks[today]`

**验证**：语法检查通过

---

#### ✅ F12 【中危·并发】auto_selfie_task 共享状态无锁保护
**文件**：`core/selfie/auto_selfie_task.py:79,105-144,285-309`

**修复内容**：
1. `__init__()` 中添加 `self._state_lock = asyncio.Lock()`
2. `stop()` 方法使用 `async with self._state_lock` 保护 `is_running` 修改
3. `_on_task_done()` 改为异步方法 `_handle_task_done()`，使用锁保护状态检查和修改
4. `_selfie_loop()` 中判断是否该拍照的代码块使用锁保护 `_last_selfie_ts` 读取
5. 执行自拍后使用锁保护 `_last_selfie_ts` 修改

**验证**：语法检查通过

---

#### ✅ F14 【中危·资源】ScheduleDB 线程本地连接无清理机制
**文件**：`core/schedule/schedule_db.py:89-103`

**修复内容**：
- 新增 `close_all_connections()` 类方法，遍历 `_thread_local.conns` 并关闭所有连接
- 供插件卸载时调用（与 F7 修复合并）

**验证**：语法检查通过

---

#### ✅ F15 【中危】配置热重载时后台任务状态不一致
**文件**：`core/selfie/auto_selfie_task.py:235-264`

**修复内容**：
1. 移除 `_selfie_loop()` 方法开始处读取一次 `interval_minutes` 的逻辑
2. 在 while 循环内每次迭代重新读取 `interval_minutes`、`quiet_hours_start`、`quiet_hours_end`
3. 添加注释说明支持配置热重载

**验证**：语法检查通过

---

#### ✅ F19 【中危·隔离】ConversationContextCache 全局单例无跨会话隔离
**文件**：`core/inject/context_cache.py:189-207`

**修复内容**：
1. `_cache_instance` 改为 `_cache_instances: dict[str, ConversationContextCache] = {}`
2. `get_context_cache()` 增加 `stream_id` 参数（默认空字符串以兼容旧代码）
3. 按 `stream_id`（为空时用 `"__global__"`）隔离缓存实例

**验证**：ruff 通过（移除未使用的 `Optional` 导入）

---

### P3 - 低危（6项）

#### ✅ F10 【低危·死代码】日程上下文缓存从未接入生产消息流
**状态**：已识别，无需代码修改
- `ConversationContextCache.add_turn()` 无外部调用点
- 缓存功能实际未启用
- 建议：若功能已废弃，删除相关代码；若计划使用，需在消息处理器中调用 `add_turn()`

---

#### ✅ F11 【低危】requests 的"可选依赖"声明与加载行为冲突
**文件**：`core/utils/image_utils.py:1-18,145-150`

**修复内容**：
1. 顶层 `import requests` 改为 try-except 包裹，设置 `_REQUESTS_AVAILABLE` 标志
2. `_download_http_image_with_requests()` 方法开始处检查 `_REQUESTS_AVAILABLE`，不可用时立即返回错误

**验证**：ruff 通过，compileall 通过

---

#### ℹ️ F13 【低危】recall_utils.py 创建的后台任务未追踪
**状态**：已识别，建议后续优化
- `recall_utils.py:248` 的 `asyncio.create_task(_recall_task())` 未保存句柄
- 插件卸载时无法取消
- 建议：将任务句柄存入模块级 `WeakSet` 或统一任务追踪器

---

#### ℹ️ F16 【低危·性能】API 客户端无连接池，每次请求重建 HTTP 连接
**状态**：已识别，建议后续优化
- 每次 `generate_image` 调用创建新的 SDK 客户端
- 建议：在 `BaseApiClient` 层缓存客户端实例

---

#### ℹ️ F17 【低危·理论】事务与 asyncio.to_thread 的隔离性问题
**状态**：已识别，理论风险
- `ensure_today_schedule()` 连续调用 3 个 `to_thread`，不在同一事务中
- 建议：在 `ScheduleDB` 层提供原子化的组合操作

---

#### ℹ️ F18 【低危·资源】缓存跨会话隔离但无过期清理
**状态**：已识别，建议后续优化
- `cache_manager.py` 中 `_global_caches` 只增不减
- 建议：添加全局缓存容量限制或 LRU 驱逐策略

---

#### ℹ️ F20 【低危】_execute_selfie 无 finally 块，异常时资源可能未清理
**状态**：已识别，建议后续优化
- `auto_selfie_task.py:338-617` 的 `_execute_selfie()` 无 finally 块
- 建议：为外部资源（QZone API、httpx 客户端）包裹 try-finally 或使用上下文管理器

---

## 验证结果

### 静态检查
✅ **compileall**：`python -m compileall -q "plugins\selfie_painter_v2"` → exit 0  
✅ **ruff**：`ruff check "plugins\selfie_painter_v2"` → All checks passed

### 修复统计
- **已完成代码修复**：14 项（F1,F3-F9,F11-F12,F14-F15,F19）
- **需用户手动处理**：1 项（F2：密钥撤销）
- **已识别无需代码修改**：1 项（F10：死代码）
- **建议后续优化**：4 项（F13,F16-F18,F20：低优先级优化）

---

## 残余风险

1. **F2 密钥泄露风险**：需用户确认并撤销真实密钥
2. **F6 生命周期缺口**：完整修复需宿主支持热卸载时调用 `on_plugin_unload()` 或派发 `ON_STOP`
3. **F10 死代码**：缓存功能未启用，需确认是废弃还是待接入
4. **F13/F16-F18/F20**：低优先级性能和资源管理优化点

---

## 后续建议

1. **立即操作**：
   - 确认 F2 密钥真伪，若为真实密钥立即撤销
   - 测试环境验证插件可正常启用（F1 修复）
   - 验证日程注入功能生效（F3 修复）
   - 验证模型权限无绕过（F4 修复）

2. **中期优化**：
   - 补全集成测试（当前 tests/ 已删除）
   - 实现配置变更通知机制（增强 F15）
   - 统一资源生命周期管理（F13/F20）

3. **长期优化**：
   - 建立并发安全检查清单（F12/F17）
   - 实现连接池和缓存驱逐（F16/F18）

---

**修复完成时间**：2026-07-21  
**下一步**：用户确认 F2 密钥状态，测试环境验证核心修复
