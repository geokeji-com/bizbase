<!-- ratchet: kind=decisions status=confirmed by=user on=2026-11-18 -->
# 约束与决策记录

本文件记录用户明确指令、已接受的取舍及 Agent 作出的可逆组织决定。未接受的业务方案仍在候选材料或决定清单中，不据此视为已确认。

## 当前明确指令

- 最新指令见 D-012：撤回第 01 轮实现，删除新建实例，回到原 8080 预览的 Build；本次只恢复该状态。
- 用户于 2026-11-18 显式调用 ratchet，要求继续推进，并明确竞对材料、口述与 SOP、既有仓库均可质疑；该指令不构成对此前整套模型或数据归属建议的确认。

## 决策记录

### D-001 复用既有文档位置，建立循环索引（2026-11-18；本轮工作区检查）——brief 映射由 D-005 调整

- 背景：已有项目定位、候选模型和研究文档，但没有循环配置或已确认的轮次。
- 类型：双向门，Agent 决定。
- 决定：配置映射既有定位与模型；历史内容保持 review。私有仓库明细不复制进公开仓库，新增材料引用抽象证据编号。
- 理由：便于复核现有工作，避免额外生成一套同名长期资产；可调整映射。
- 影响：docs/agents/ratchet.md、AGENTS.md、docs/bizbase.md、docs/business/2026-11-17-geo-service-model.md。

### D-002 首轮整体规划，后续行动按 ratchet 小轮次交付（2026-11-18；用户明确指令）

- 背景：用户要求采用自然式规划五步，调整此前先选小切片再继续确认的推进方式。
- 类型：单向门，用户裁决（项目推进基线）。
- 决定：本次首轮集中完成目标、成果画面、头脑风暴、组织管理；第五步的具体行动纳入 ratchet 实施轮次，争取每天至少发布一个版本。前四步不每轮重新进行；材料仍可依证据修正。
- 理由：先把整体方向与成果组织清楚，再用小步交付推进。此前文章回链方案恢复为候选，旧决定清单未答的三项不视为接受。
- 影响：docs/planning/、docs/cycle/sheets/decision-sheet-02.md、backlog.md、proposals/first-slice.md、docs/agents/ratchet.md、docs/bizbase.md、候选模型入口；旧清单归档留证。
- 边界：本条确认推进方式，不自动确认数据模型或生产发布权限；整体规划与发布定义随后分别由 D-003、D-004 裁决。

### D-003 接受整体规划与真实使用场景成果基线（2026-11-18；用户“整体规划认可，两项接受”）

- 背景：清单 2 请求评审四步整体规划及成果判断。
- 类型：单向门，用户裁决。
- 决定：接受 docs/planning/ 的整体规划基线，以其中六类真实场景判断成果；重点验证跨应用事实和权限一致、历史可追溯、新应用可接入。早期用至少两个独立消费者与真实服务验证，逐版本扩展。
- 理由：用可检验业务结果推进，而非以 App 或表数量作为完成依据；完整成果不要求在一个版本完成。
- 影响：docs/planning/natural-plan.md、opportunities.md、delivery-map.md，docs/cycle/sheets/decision-sheet-02.md、backlog.md，docs/bizbase.md、候选模型状态说明。
- 边界：机会池与候选版本不是全部实施承诺；尚未核实的表结构、样例、写入归属和具体授权细则不随整体规划自动确认。

### D-004 日版本交付以本地或测试环境可用增量计数（2026-11-18；用户“整体规划认可，两项接受”）

- 背景：清单 2 请求确认每日版本的交付环境和计数方式。
- 类型：单向门，用户裁决。
- 决定：初期日版本交付到约定本地/测试验收环境，须可访问、可操作、通过当轮验收并留记录；原型、测试与生产分别标明，文档和代码提交不代替软件发布。
- 理由：持续看到可用增量，并使发布记录与实际可用状态一致。
- 影响：docs/planning/delivery-map.md、natural-plan.md，docs/cycle/sheets/decision-sheet-02.md，后续各实施轮 release/review。
- 边界：争取每天至少一个版本；未达验收就如实记录。生产发布、数据迁移、权限扩大、付费投放仍依具体授权执行。

### D-005 将已获确认的整体规划映射为 brief（2026-11-18；Agent 组织调整）

- 背景：用户明确确认的是整体规划；旧 docs/bizbase.md 仍混有此前未裁决的具体建议。
- 类型：双向门，Agent 决定。
- 决定：brief 指向 docs/planning/natural-plan.md，使用已批准的基线；旧定位文档保留为历史背景。领域模型仍指向既有候选模型并保持 review。
- 理由：准确体现已确认与未确认的边界，避免反复要求批准同一目标，也避免扩大确认范围。
- 影响：docs/agents/ratchet.md、docs/bizbase.md；仅调整 D-001 的 brief 映射，其私有证据保护等约束继续有效。

### D-006 以当前可评审的最小模型作为领域模型入口（2026-11-18；Agent 组织调整）

- 背景：整体规划已确认；历史完整 GEO 候选包含尚未触及的规则，不应要求用户一次批准所有未来对象。
- 类型：双向门，Agent 决定。
- 决定：domain_model 改为 docs/business/directory-model.md，并保持 review；原 GEO 模型仍保留为扩展候选。模型语义、授权与快照方案通过清单 3 另行裁决，不因入口映射而被接受。
- 理由：让本次评审只覆盖拟实施的最小变化，同时保留全局规划和历史证据。
- 影响：docs/agents/ratchet.md、docs/business/directory-model.md、directory-model-views.md、2026-11-17-geo-service-model.md，docs/cycle/sheets/decision-sheet-03.md、proposals/directory-query.md、proposals/directory-acceptance.md、backlog.md、evidence.md，docs/bizbase.md、GLOSSARY.md；调整 D-005 的领域模型映射说明，brief 映射不变。

### D-007 接受目录最小模型与来源引用身份（2026-11-18；用户“最小模型和三项接受”）

- 背景：清单 3 第 1 项及其引用的 v0.1 模型请求确认两个消费者如何关联同一客户与优化对象。
- 类型：单向门，用户裁决。
- 决定：确认 directory-model.md v0.1 及配套关系/状态图；首版只读，以来源系统和原始 ID 识别客户与对象，新增客户引用作为授权锚点，资料由来源维护，不按名称合并或自动映射 ERPNext 客户。
- 理由：以真实关系验证接入，保留已有身份与修改责任。
- 影响：docs/business/directory-model.md、directory-model-views.md，GLOSSARY.md，docs/cycle/sheets/decision-sheet-03.md、proposals/directory-query.md、backlog.md、evidence.md，docs/agents/ratchet.md、docs/bizbase.md、后续第 01 轮材料。
- 边界：不确认完整 GEO 候选模型，不授权来源主库迁移；后续新增模型变化单独记录。

### D-008 接受按客户显式授权的目录边界（2026-11-18；用户“最小模型和三项接受”）

- 背景：清单 3 第 2 项要求明确目录读取权，现有框架缺省与分享行为不能直接表达所需边界。
- 类型：单向门，用户裁决。
- 决定：复用 Frappe 用户、角色和客户授权记录；人和专用机器账号分别明确授权，未授权拒绝，不继承客户层级。授权只覆盖该快照中此客户全部已接入对象的最小目录字段，不扩展到合同、服务或报告；统一判定、已提交撤权后的新请求拒绝，客户引用禁止分享。业务审计和框架认证日志按模型区分。
- 理由：客户归属、来源返回和人员/应用权限是不同事实，必须独立验证。
- 影响：docs/business/directory-model.md、directory-model-views.md，GLOSSARY.md，docs/cycle/sheets/decision-sheet-03.md、proposals/directory-acceptance.md、backlog.md、evidence.md、后续第 01 轮验收与 readback。
- 边界：仅本地隔离内部验收；不改变现有 U-01 权限，不开放客户/渠道，不签发生产权限。机器账号只代表应用，不代表其最终用户。

### D-009 接受真实历史快照作为首版本地数据（2026-11-18；用户“最小模型和三项接受”）

- 背景：清单 3 第 3 项在已核实历史样本和未验证的当前在线接入之间选择首版路径。
- 类型：单向门，用户裁决。
- 决定：首版使用 S-01 真实历史快照，明确显示 2026-11-02 数据日期与快照属性，真实文件保存在私有目录；内部页面和独立客户端共同验收。实时源后续接入，不能把历史目录解释为当前在服、合同周期或生产权限。
- 理由：先验证可操作的身份及授权路径，避免用未知的在线条件阻塞本地版本。
- 影响：docs/business/directory-model.md、directory-model-views.md，docs/cycle/sheets/decision-sheet-03.md、proposals/directory-query.md、proposals/directory-acceptance.md、backlog.md、evidence.md、后续第 01 轮一页纸与验收。
- 边界：真实成功样本与隔离的合成边界测试分别验证；快照不进 Git、镜像或公开下载入口。仍须按 D-004 完成实际软件验收才计版本。

### D-010 采用独立本地环境与受版本管理的 App 源码（2026-11-18；Agent 工程组织选择）

- 背景：已有固定镜像可复用，但现有运行容器没有业务源码挂载；直接编辑其中的文件无法形成可复现交付。
- 类型：双向门，Agent 决定。
- 决定：App 放 apps/bizbase/，原型放 prototypes/directory/；使用独立 bizbase-r01 Compose 项目和 bizbase-acceptance.localhost 站点，拟用本机 8081 验收、8082 原型，启动前复核。新项目独占数据库和卷，基于已核验固定镜像派生；当前 8080 项目不参与本轮写入。工程预算与验证方式记入第 01 轮材料。
- 理由：利用已有框架环境，保持源码可追溯、原型隔离和交付可重复；这些路径和端口可按冲突检查调整。
- 影响：docs/cycle/rounds/01/one-pager.md、readback.md、preflight.md、acceptance.md；未来 apps/bizbase/、deploy/local-directory/、prototypes/directory/、scripts/directory/、tests/directory/。
- 边界：此项不是 readback 确认，也不代表已运行安装、迁移或发布。

### D-011 第一轮由 Agent 自主执行至本地交付（2026-11-18；用户“工程计划确认”，并要求中间不再确认）

- 背景：用户希望观察第一轮在无人介入时的完整交付能力。
- 类型：单向门，用户裁决（本轮执行授权）。
- 决定：确认第 01 轮 readback；第一轮继续按模型、界面、逻辑、验收、发布、复盘推进，中间无需用户确认。原型由 Agent 实际试用、检查与修正后进入服务接入；必要的本轮工程修订由 Agent 记录并独立审查，最终报告真实结果。
- 理由：按用户最新明确指令完成一次自主闭环，不因先前 skill 的中间确认步骤再次打断。
- 影响：docs/cycle/rounds/01/readback.md、后续原型检查、release/review；docs/agents/ratchet.md。
- 边界：沿用 D-007—D-009 的本地隔离范围、来源与权限规则；不扩大到生产、付费投放或他人系统写入。Agent 自验不冒充用户亲自试用或事后亲自确认复盘；若需工具标注确认，使用 delegated-agent 并引用本授权。

### D-012 撤回首轮实现，回到原预览的 Build（2026-11-18；用户明确指令）

- 背景：用户认为当前实现可能偏离预期，要求“把我们刚才的动作还原，并且删除新建的那套实例”，先回到原预览直接使用 Build 的状态。
- 类型：用户裁决，授权撤回本轮实现并删除其专属实例及数据卷。
- 决定：精确撤回 8e5afa8、61f0c0c 两个实现提交，删除 bizbase-r01 专属容器、卷、网络和本轮镜像；保留原 bizbase 项目、frontend 站点、ERPNext/CRM、账号及原数据，使用 8080 的 /desk/build。
- 影响：覆盖 D-010 的独立环境路线，终止 D-011 的本轮继续执行；本轮发布改为历史记录，当前事实见 rounds/01/withdrawal.md。
- 边界：此前整体规划、模型讨论、研究及用户未提交改动保留；既有私有备份留档。此次不创建新模型、不迁移快照、不更改原站点权限或开发模式；后续工作按新的具体指令推进。
