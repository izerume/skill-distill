<img src="assets/icon.svg" width="64" height="64" alt="">

# Skill Distill

**技能入口：[SKILL.md](skills/skill-distill/SKILL.md)**

将相关 Agent Skills 蒸馏为更易复用的技能，同时记录来源、检查原有能力，并维护项目内的产物版本。

交付物是一份 [Agent SKILL](skills/skill-distill/SKILL.md)：agent 按其中的方法分类、选材、构建和验证；内部 Python 脚本辅助处理指纹、快照、记录及恢复。脚本本身不调用模型。

## 使用前提

- 使用支持 Agent Skills 的 agent。
- 已有 `npx skills` 管理的源技能；本地手写技能也可以作为输入。
- Python 3.10 或以上。运行脚本和单元测试仅需标准库。

`npx skills` 负责源技能的安装和更新。本 SKILL 读取已安装内容，只有你明确要求更新，agent 才更新蒸馏产物。

## 安装和调用

在要使用技能的项目目录中运行：

```text
npx skills add izerume/skill-distill --skill skill-distill
```

上述调用使用项目范围，不带全局安装参数。安装后通过 `$skill-distill` 调用。

也可以让 agent 直接读取本仓库的 [SKILL.md](skills/skill-distill/SKILL.md)。常见请求：

```text
用 $skill-distill 看看我的技能库。先按名称和描述分类，
列出值得一起蒸馏的组，暂时不要深入分析。
```

```text
用 $skill-distill 合并这几份写作技能，保留各自的操作模式。
把新技能放到当前项目的 distilled/writing-workbench，
用少量代表任务快速比较原版和融合版。
```

```text
检查 writing-workbench 的来源是否变化，先不要更新。
```

```text
更新 writing-workbench，基于本机已安装的源技能重蒸馏，
快测通过后切换；如果有我的本地修改，先保留。
```

```text
把 writing-workbench 恢复到 r000001。
```

## 工作方式

1. **先分类。** 初筛只读名称和描述，按任务领域分组，并记录工作流、方法、工具、资料等角色。
2. **按组深入。** 选择相关组，再读取正文、资源和调用边界，比较保留、单项压缩、共享参考或融合。
3. **保留能力。** 冻结完整输入，记录源行为和对应位置，合并共享部分，保留任务、平台及流程分支。
4. **实际检查。** 保存真实输出与文件结果；快速检查通过后即可停止，完整评测按用户要求执行。
5. **维护版本。** 记录源修订、蒸馏方法和具体产物；检查只读，更新和恢复由用户明确触发。

分类数量不等于最终技能数量。文件体积也不等于模型 token 或费用；性能结论应对应实际执行的任务范围。

## 版本管理

产物可以继续使用项目内原有路径，历史和证据保存在 `.skill-distill/`。

- 完整内容指纹覆盖入口、脚本、参考及资源。
- 已知的历史源快照可以导入；缺失的历史照实记为未知。
- 候选封存和切换分开，证据须对应实际产物。
- 来源变化、其他会话切换或本地手改会阻止覆盖。
- 恢复直接使用保存的旧包，不重新调用模型生成。
- 切换中断后，agent 可以按操作记录恢复一致状态。

详细流程和内部命令见 [版本维护](skills/skill-distill/references/versioning.md)。已核对的 `skills@1.7.4` 中，`npx skills check` 会进入更新流程，因此这里的只读检查不使用它。

## 文档与辅助脚本

| 入口 | 用途 |
| --- | --- |
| [分类说明](skills/skill-distill/references/classification.md) | 轻量分组、角色标签和候选组 |
| [目标选择](skills/skill-distill/references/target-selection.md) | 根据源证据选择处理方式 |
| [行为契约](skills/skill-distill/references/contracts.md) | 记录和协调源能力 |
| [评测方法](skills/skill-distill/references/evaluation.md) | 快测、配对检查及证据解释 |
| [证据格式](skills/skill-distill/references/evidence-format.md) | 来源快照、契约和比较结果 |
| [术语](GLOSSARY.md) | 源修订、蒸馏版本和恢复的含义 |

`scripts/skill_distill.py` 提供 `classify`、`select`、`snapshot`、`validate`、`compare`；`scripts/versioning.py` 提供内部版本操作。路径均相对 SKILL 目录。通常由 agent 按文档调用，用户不必手工编写中间 JSON。

## 开发验证

在仓库根目录运行：

```text
python -X utf8 -B tests/run_tests.py
```

测试覆盖公开操作及磁盘结果，包括只读检查、历史输入、证据绑定、来源替换、过期候选保护和真实进程退出后的恢复，不调用模型或更新真实安装。

GitHub Actions 配置在 Windows 和 Linux 上运行同一组测试。研究原始数据、个人路径记录和本机生成的蒸馏产物不属于核心发布内容。
