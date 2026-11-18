<!-- ratchet: kind=readback status=confirmed by=user on=2026-11-18 -->
# 第 01 轮工程计划（readback）

> 历史计划：D-012 已撤回本轮实现和独立实例，终止此计划的继续执行。当前只恢复原 8080 Build，详见[撤回记录](withdrawal.md)。

状态：用户已明确“工程计划确认”，并按 D-011 授权第一轮全程自主执行。模型及三项取舍已由 D-007—D-009 确认；执行路径的可逆选择记录为 D-010。中间检查由 Agent 实际执行和留证，不冒充用户亲自试用。

本文保留启动前计划与检查基线；实际实施进度、调整和结果以 [execution.md](execution.md)、[release.md](release.md) 为准。

## 我理解的目标
<!-- section: understanding -->

交付一个本地“客户目录”和独立客户端：两者以真实 S-01-D 的来源 ID 查询到 S-01-O，显示 2026-11-02 数据日期；未明确获准该客户的人或应用都无法读取。来源身份、客户粒度、只读快照分别落实 D-007、D-008、D-009；原始真实值由私有快照提供，不写入公开仓库。

事实：[准备证据](preflight.md)已核对镜像、工具链和原始样本；已提取 2 客户身份、1 对象的私有最小摘录，尚未激活。推断：复用现有固定框架镜像可减少重新搭建成本，但新 App 的构建依赖、安装和浏览器路径仍需实测。预算及成功标准沿用[一页纸](one-pager.md)。

## 参照与复用
<!-- section: reuse -->

| 环节 | 复用什么（来源） | 自研什么及理由 |
|---|---|---|
| 数据模型 | 当前 Frappe User、Role、User Permission、Integration Request、Permission Log；E-09 | BB Customer Reference 仅作来源身份锚点；ERPNext Customer 不是当前来源客户的自动对应物 |
| 页面与交互 | Frappe Desk 页面外壳、现成表单/列表样式、错误提示；管理配置沿用原生页面 | 一个受控目录页面；普通原生引用列表不满足专用授权边界，不能直接公开 |
| 逻辑与接入 | 当前 Frappe 认证、DB/安装机制及原生日志；E-07 来源稳定 ID | 统一显式授权、字段白名单、快照读取/校验和安全审计；原生无授权缺省与分享行为不满足 D-008 |

## 第一步：数据模型
<!-- section: model -->

1. 在 apps/bizbase/ 建标准 App 目录，采用与已安装 Frappe 版本匹配的 pyproject 并固定构建后端；不创建嵌套 Git。派生固定 ARM64 镜像并建立隔离站点，安装当前 Frappe/ERPNext/CRM 组合与 BizBase。先核验依赖及安装，再进行后续阶段。实际采用最小标准脚手架，固定 flit_core wheel 校验摘要后离线安装；运行结果见 execution.md。
2. 唯一新增业务表 BB Customer Reference：框架生成 name，必填 source_system、source_customer_id、display_name；数据库对前两个字段建复合唯一约束。来源 ID 按字符串保存且创建后不可改；展示名来自快照。真实目标行取私有 S-01-D 的来源系统、交付客户 UUID、原名称；不是新造客户。配置记录的内部 name 不替代外部来源身份。
3. 注册 BB Directory Reader Role；引用原生 CRUD 只给配置管理员，普通人员和机器账号通过业务接口读取。禁止引用分享的控制器规则与唯一性检查纳入模型测试。User Permission 使用显式引用值并核对适用范围；未授予任何测试身份生产权限。
4. 顺序：建空表及约束 → 核验空库安装/重复迁移/模型测试。M 阶段只用独立合成夹具测试结构，不加载真实快照，不实现客户查询服务。真实快照启用及测试身份授权在 C 阶段。

## 第二步：页面与交互
<!-- section: view -->

1. 在 prototypes/directory/ 做独立可点击原型，计划仅监听 127.0.0.1:8082；当前尚未启动。合成内容明确标为原型，原型不读私有快照，不带真实凭证。
2. 用户可体验：选择客户 → 看优化对象和数据日期 → 切换加载、空、失败、无权状态 → 重试/返回；授权管理员的启用/停用结果以原型场景表达。测试场景切换器只在原型范围。
3. 普通产品页面仅保留客户选择、对象列表、数据日期、来源异常与必要操作；不显示方案编号、开发解释或虚构经营指标。最终目录页计划置于新站点的 /desk/bb-directory，实际生成路由在实现时核对后再交付可点击入口。
4. 按用户新增 D-011 授权，由 Agent 实际操作原型、检查状态并修正后进入 C 阶段，不等待用户中途确认；原型自验留证，不能宣称是用户亲自试用。

## 第三步：逻辑与接入
<!-- section: logic -->

1. 实现同一版本化目录 RPC 的客户列表/对象读取；入口从当前认证会话取得身份。人员用浏览器会话，独立客户端用单独 Frappe 机器账号的服务端凭据；不接受任意 actor/user 作为授权身份，不把密钥存浏览器。
2. 每请求核对 User.enabled、实际启用角色、适用此目录的显式 User Permission、客户引用和有效快照；不用缓存缺省或 Admin 特权放行。列表零授权拒绝；详情越权与不存在采用相同响应。输出限定已确认字段。
3. 私有目录只读挂载给后端/验收进程，路径来自受控服务端配置，不接受请求传路径。读取一次版本清单，校验摘要与关系，再返回这个版本的数据；缺失、破损、未知版本明确失败。
4. 管理命令先验证不可变文件，再在数据库事务中准备整组引用；准备成功后才原子切换有效版本指针。失败时不切换；单次读取固定一个版本，不因后台切换混合数据。数据开关和版本指针仅配置管理员可改，完整失败注入见 C1/C2/F1。未激活的准备记录不作为目录结果。
5. 在隔离站点建立 reader/client/parent-reader/no-grant 等测试身份；不改旧站点 U-01。真实路径只用 S-01，空态/并发/故障使用分离的合成夹具。机器客户端必须请求 API，不能直接读快照文件。
6. 只读业务方法的审计复用 Integration Request；先持久化脱敏结果再返回或抛业务拒绝。当前辅助函数会 commit 整个事务，因此此入口禁止混入业务写入；审计失败不返回目录。框架认证前拒绝单独验日志。User Permission 正常配置变更使用 Permission Log，测试授权在安装迁移完成后创建，避免安装态跳过变更日志。
7. 容器当前源码默认 Integration Request 清理配置为 90 天（frappe/hooks.py:537–554），Permission Log 不在该默认清理表。新验收站点启用前读取实际 Log Settings/调度状态并记入发布；首版调度器停用不意味着日志永久保存。审计仅管理角色可读，不承诺不可篡改。

## 安全
<!-- section: security -->

- 触及真实历史客户名称/ID、隔离测试账号、应用读取凭据和引用授权。最可能的风险是原生资源/分享旁路或高权限账号掩盖越权；普通身份验收、引用禁止分享、全部入口拒绝测试是发布条件。
- 项目 bizbase-r01 独占数据库/卷/网络，站点 bizbase-acceptance.localhost，计划 127.0.0.1:8081；DB/Redis 不映射宿主端口。原型仅 127.0.0.1:8082。启动前重新检查名称、端口及挂载，命令明确指定项目和私有环境文件，禁止默认操作旧 frontend。
- 私有摘录和凭据不进构建上下文、Git、浏览器存储或公开下载；截图/详细证据含真实数据时只保留私有目录。新环境的测试凭据现场生成且不打印；没有生产源凭据请求或生产写入。

## 预演失败
<!-- section: premortem -->

1. 派生构建依赖下载或版本不兼容：先用固定基础镜像验证脚手架和构建后端，复用现有框架资源；失败不动旧预览，也不把已写脚手架算交付。
2. 原生权限/缓存/分享导致漏读：零授权、角色停用、撤权提交后新请求、原生资源和分享分别测试；以直接授权事实判定。
3. 快照、审计或恢复出现部分成功：完整文件先校验、版本指针后切换；日志失败不放行；恢复同时匹配数据库、站点配置、文件及镜像，单独验证。

## 怎么关掉、怎么回滚
<!-- section: rollback -->

- 配置管理员关闭原生 DefaultValue 中 `bizbase_directory_state.enabled` 后，后续新请求返回明确不可用；关闭不删快照、引用或授权。开关和 active 版本在同一状态记录内原子更新，按请求直接读取，不能依赖进程缓存延迟。
- 不够时停止 bizbase-r01 并保留卷/日志；不执行 down -v。新的验收站点有数据后，迁移前备份 DB、配置、文件到其卷外私有目录，恢复使用匹配镜像并验证 A1/A2/权限。首版尚无前一 BizBase 软件版本时，恢复到本轮新建隔离环境的安装前备份或干净重建，而不是操作旧 8080。

## 我会动的文件
<!-- section: files -->

- apps/bizbase/：pyproject、hooks、modules、安装/迁移；bizbase/bizbase/doctype/bb_customer_reference/；bizbase/bizbase/page/bb_directory/；bizbase/directory/{policy,snapshot,service,audit}.py、bizbase/api/directory.py；对应 Frappe 测试。
- prototypes/directory/：独立原型及合成场景；不进入生产路由或镜像。
- deploy/local-directory/：Containerfile、独立 compose.yaml、私有数据准备专用 compose.data.yaml、README；所有应用进程采用相同派生镜像。验收不依赖宿主源码绑定，固定 App 提交。
- scripts/directory/：环境守卫、引导、私有快照准备/启用、独立客户端、验收入口和备份恢复；tests/directory/：合成夹具、浏览器验证及其锁定依赖。
- .github/workflows/directory.yml：公开合成检查；完整真实站点验收仍在本地执行。docs/agents/ratchet.md 配置实际 test_cmd，rounds/01/ 保存发布和复盘。
- 私有：~/.codex/private/bizbase-round01/ 保存数据、凭据、备份及含真实信息证据；与公开产物分离。其余历史源码、旧部署文件、旧站点和其他仓库不在本轮修改范围。

## 我怎么验证
<!-- section: verify -->

| 验收编号 | 计划脚本/命令 | 在哪里验证 |
|---|---|---|
| A1/A2、真实数据日期/字段 | scripts/directory/verify_round01.py + 独立 consumer.py；tests/directory/browser/ 的真实路径 | 新本地验收站点，实际人员和机器账号；真实数据证据私有 |
| A3/A4、B1、C1—C4、D1—D7、F1 | bench --site bizbase-acceptance.localhost run-tests --app bizbase 的对应 unittest，结果按行编号；必要 HTTP 回归补充 | 同框架的新隔离测试数据，合成载荷；不能写旧 frontend |
| B2、D3/D4 两入口、D8/D9、E1 | tests/directory/browser/ + HTTP 验证脚本 | 浏览器与独立客户端，覆盖 Cookie/token、原生接口和认证前拒绝 |
| F2 | scripts/directory/verify_round01.py 的安装/重建/重启/恢复检查 | 新项目；同时核对旧项目资源身份与访问状态 |

聚合脚本必须检查项目/site/绑定地址，执行完整必需场景并生成清单；缺真实样本、缺凭据、跳过必要场景或只有 HTTP 200 均非通过。脚本实际跑通后才配置 test_cmd；当前不声称这些计划文件已存在。CI 只跑不含真实数据的快速检查，本地完整验收及 CI 执行状态分别报告。

## 我不确定、需要确认的
<!-- section: questions -->

无待答问题。用户已确认工程计划，并按 D-011 将本轮中间确认交由 Agent 自主完成；先 M、再实际试用 V、再 C，直至本地验收和发布。授权不扩大到生产部署或其他业务范围。
