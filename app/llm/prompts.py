import re

ANALYSIS_PROMPT = """你是课程文档视觉理解器。图片是主要输入，辅助文本仅用于看不清时核对。
读取页面布局、标题层级、表格列、合并单元格、缩进与跨页关系，生成文档明确列出的课程知识目录。

语义边界：
- 课程内容必须保留；学习目标、题型、错因、能力、解释不得成为节点或 SCOPE。
- 不要凭学科常识补充、改写或现代化替换原文内容。
- 判断某项是否属于课程内容，首要依据是其所在表格列及视觉关系，不得只按动词或关键词判断。

层级与粒度：
- 文档明确出现的册别、年级、学期或课程阶段名称，必须按页面原文保留为 LEVEL 节点。
- 只有页面或辅助文本明确给出具体年级、学期、上下册时，才能输出对应具体年级节点。
- 只有“初中”或“高中”等学段证据时，只保留该学段，不得推断具体年级。
- 完全没有年级或学段证据时，不得默认输出“初一上”或任何具体年级；直接从明确课程层级开始。
- 上一批路径摘要只有明确包含年级原文时才可延续，不得把其他批次年级套到当前页面。
- 目录或表格中列在册别、年级下面的章名、单元名仍是子 LEVEL，不能写成该册别的 SCOPE。
- 页面明确编号的章、节、项目、课程内容条目应按视觉层级输出为 LEVEL。
- 三列表格若按“章 / 项目 / 具体内涵”等列展示，并分别使用 1、1.1、1.1.1 这类层级编号，
  必须依次输出为父子 LEVEL；不得因为列名是“具体内涵”就把明确编号的第三级条目降为 SCOPE。
- 未编号但并列列出的概念、方法或性质，只有在页面语义表明它们能独立承担知识归类、
  且共享谓词的作用范围明确时，才拆为更深一级 LEVEL。
- 谓词作用范围不明确、拆分会补入原文没有的“计算、应用、性质”等含义时，不得猜测；
  保留原句为最近节点的 SCOPE。
- SCOPE 只用于最近节点不可再可靠细分的课程内容原文，绝不能用多个 SCOPE 代替一组明确子节点。

scope 尽量复制课程内容原文；不能可靠读取时不要输出 SCOPE。
只输出以下纯文本协议，不要输出 JSON、Markdown、解释或推理：

BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 名称
LEVEL 2 | 大章名称
LEVEL 3 | 编号项目名称
LEVEL 4 | 编号具体内涵
SCOPE | 最低层节点下未单独编号的原文范围
UNRESOLVED | 页码 | 原因
END_KNOWLEDGE_TREE

LEVEL 从 1 开始，相邻最多向下一级。只允许 BEGIN、LEVEL、SCOPE、UNRESOLVED、END 指令。
"""


MERGE_PROMPT = """合并下列按页批次的知识目录。
只允许合并跨页节点、删除重叠窗口产生的完全重复节点、修正层级延续，并保持原顺序和原文。
不得创造知识点，改写名称，扩写 scope，补充常识，或删除明确课程内容。

必须保留批次中出现的册别、年级、学期或课程阶段节点，不得省略、缩写或把无年级批次归入任意具体年级。
必须按原文关系恢复“学段 → 册别/年级 → 章/单元 → 课程内容”的相对层级。
目录批次中的章名和详细批次中的同一章只保留一个节点，并把详细条目挂到该章下面。
不得把所有册别、章节和课程条目压成同一 LEVEL，不得留下空的册别重复节点。
“章 / 项目 / 具体内涵”等多列表格中已由 1、1.1、1.1.1 表明的层级必须全部保留为 LEVEL，
不得在合并时把最低一级编号条目改成 SCOPE。

同一节点最多一个 SCOPE；目录中的章名列表必须转换为子 LEVEL，不能保留为重复 SCOPE。
遇到下一册别或年级节点前，后续章节和课程条目必须保持在当前册别或年级之下。
只输出统一的 BEGIN_KNOWLEDGE_TREE 到 END_KNOWLEDGE_TREE 纯文本协议。
"""


PRIMARY_DSKP_ANALYSIS_PROMPT = """你是马来西亚华文小学数学 DSKP 课程文档视觉理解器。
图片是主要输入，辅助文本只用于看不清时核对。

只抽取文档明确列出的数学课程内容：
- LEVEL 1：页面明确出现的年级，如“一年级”。不得根据批次顺序猜测年级。
- LEVEL 2：页面明确标示的学习领域，如“数与运算”、“测量与几何”。不得把课题名称提升为学习领域。
- LEVEL 3：课题，如“1.0 100 以内的整数”。
- LEVEL 4：“内容标准”列的数学内容，如“1.1 数值”。
- SCOPE：与该内容标准同一行或合并单元格对应的“学习标准”原文。

一个内容标准对应多条学习标准时，在同一条 SCOPE 中按原顺序合并，
保留原文的子项、范围、数值、术语和标点。不得自由总结或改写。
同一个 LEVEL 4 节点后最多只能输出一行 SCOPE；必须先收集完所有对应学习标准，
再一次性输出合并后的 SCOPE，绝不得为同一节点输出第二行 SCOPE。
“解决问题”如果出现在内容标准列，它就是课程内容，必须保留。

备注列处理：
- 小学第一版完全忽略“备注”列，包括“笔记”和“活动建议”。
- 备注中的概念说明、教学顺序、例子、教具、软件、珠算盘、图片、教学法、
  STEM 或课堂组织建议都不得成为节点或 SCOPE。
- 对于备注列不输出 UNRESOLVED，直接忽略。

必须完全排除：
- “表现标准”列、级别 1–6 及其诠释；
- 每个课题前“目标：使学生能够”下的目标陈述；但该页明确出现的年级、学习领域和课题标题
  仍须按 LEVEL 1/2/3 输出，为后续内容表格批次提供真实的层级上下文；
- 导言、课程宗旨、通用学习目标、课程架构和组织说明；
- 解答问题、推理、沟通、表示、联系等通用过程能力说明；
- 心灵、态度与价值观、人文、爱国精神、21 世纪技能、高层次思维技能、跨课程元素；
- 评估方法、报告模板、教师职责、行政说明、国家原则和教育哲学；
- 题型、错因、能力、学生画像和模型的解释性概括。

一至五年级常见“内容标准 / 学习标准 / 备注”三列表。
六年级常见“内容标准 / 学习标准 / 表现标准”同页四列表。
必须根据表头、列位置、底色和合并单元格追踪对应关系，不得把右侧表现级别误作 scope。

只输出以下纯文本协议，不要输出 JSON、Markdown、解释或推理：
BEGIN_KNOWLEDGE_TREE
LEVEL 1 | 年级
LEVEL 2 | 学习领域
LEVEL 3 | 课题
LEVEL 4 | 内容标准
SCOPE | 对应学习标准原文
UNRESOLVED | 页码 | 原因
END_KNOWLEDGE_TREE

每条 LEVEL、SCOPE 和 UNRESOLVED 必须各占一个物理行。
SCOPE 内部的原文换行必须改为空格，多条学习标准之间用中文分号“；”连接。
不得输出任何不以协议指令开头的续行，不得输出“备注：”、“笔记：”或“活动建议：”行。
正确示例：
LEVEL 4 | 1.2 数值
SCOPE | 1.2.1 说出 100 以内的数目：(i) 读出数目；(ii) 说出数目；\
1.2.2 确定 100 以内的数值：(i) 展示数量；(ii) 比较数值。

只要页面出现“学习领域”及其领域名称，即使该页除此以外没有课程内容，也必须输出
LEVEL 1 年级和 LEVEL 2 学习领域；这类领域分隔页绝不能输出为空协议。
内容表格没有重复显示学习领域时，必须延续上一批路径摘要中最近一个明确学习领域，
不得使用当前课题名称臆造新的 LEVEL 2。只有真正不含任何年级、学习领域、课题标题、
内容标准或学习标准的无关页面，才输出空的 BEGIN/END 协议。
UNRESOLVED 只用于课题、内容标准或学习标准本身无法读取、或其表格对应关系无法确定的情况。
LEVEL 从 1 开始，相邻最多向下一级。只允许 BEGIN、LEVEL、SCOPE、UNRESOLVED、END 指令。
"""


PRIMARY_DSKP_MERGE_PROMPT = """合并下列马来西亚华文小学数学 DSKP 分批知识目录。
只允许合并跨页节点、删除完全重复项、修正表格跨页延续，并保持原顺序和原文。

统一层级必须为：年级 → 学习领域 → 课题 → 内容标准；
LEVEL 2 只能是分批结果中明确出现的学习领域；不得把课题名称提升为新的学习领域。
内容表格未重复学习领域时，应挂到此前最近一个明确学习领域下。
只包含年级和学习领域的分隔页批次，是 LEVEL 2 归属的权威边界：该领域持续有效，
直到后续另一个分隔页批次明确给出新的学习领域。若内容表格批次把与 LEVEL 3 课题
相同或近似的名称误写成 LEVEL 2，必须删除这个伪 LEVEL 2，并把课题挂回最近的
权威学习领域；这属于层级延续修正，不是创造知识点。
与内容标准对应的学习标准原文合并为该节点的唯一 SCOPE。
每个内容标准最多一行 SCOPE；如果分批输出对同一节点有多段 SCOPE，
必须按原顺序合并成一行，不得丢失后续学习标准。
不得创造新知识点、改写名称、扩写 scope 或根据数学常识补充内容。

必须排除整个备注列、所有表现标准、级别诠释、课题目标、活动建议、教学方法、教具、
通用过程能力、人文、态度与价值观、爱国精神、21 世纪技能、跨课程元素、
评估和行政说明。不得把六年级表格右侧的表现级别或诠释合并进 SCOPE。
“解决问题”如果来自内容标准列，必须保留。

一个批次只含无关页时，它的空协议不是错误，忽略即可。
明确应排除的内容不得在合并结果中转为 UNRESOLVED。
每条 SCOPE 必须只占一个物理行，内部换行改为空格；不得输出任何无协议指令的续行。
只输出统一的 BEGIN_KNOWLEDGE_TREE 到 END_KNOWLEDGE_TREE 纯文本协议。
"""


def prompts_for_profile(profile: str) -> tuple[str, str]:
    if profile == "general":
        return ANALYSIS_PROMPT, MERGE_PROMPT
    if profile == "primary_dskp_sjkc":
        return PRIMARY_DSKP_ANALYSIS_PROMPT, PRIMARY_DSKP_MERGE_PROMPT
    raise ValueError(f"Unsupported document profile: {profile}")


def merge_instruction_for_profile(
    profile: str, merge_prompt: str, batch_outputs: list[str]
) -> str:
    if profile != "primary_dskp_sjkc":
        return merge_prompt
    boundaries = primary_level_2_boundaries(batch_outputs)
    if not boundaries:
        return merge_prompt
    evidence = "\n".join(
        f"- 批次 {number}: {name}" for number, name in boundaries
    )
    return (
        f"{merge_prompt}\n\n"
        "以下是从分批协议中机械提取的仅含 LEVEL 2、未含 LEVEL 3 的领域分隔事件。"
        "它们是本次合并可采用的权威学习领域边界；不得用课题名替代：\n"
        f"{evidence}\n"
        "最终 LEVEL 2 只能取自上述边界事件；边界之间的全部 LEVEL 3 均归入最近的 LEVEL 2。"
    )


def primary_level_2_boundaries(batch_outputs: list[str]) -> list[tuple[int, str]]:
    boundaries: list[tuple[int, str]] = []
    for number, output in enumerate(batch_outputs, 1):
        level_2 = re.findall(r"^LEVEL\s+2\s*\|\s*(.+?)\s*$", output, re.MULTILINE)
        has_level_3 = bool(re.search(r"^LEVEL\s+3\s*\|", output, re.MULTILINE))
        if level_2 and not has_level_3:
            boundaries.extend((number, name.strip()) for name in level_2)
    return boundaries


def primary_hierarchy_review_instruction(
    merged_output: str, boundaries: list[tuple[int, str]]
) -> str | None:
    allowed = list(dict.fromkeys(name for _, name in boundaries))
    actual = re.findall(
        r"^LEVEL\s+2\s*\|\s*(.+?)\s*$", merged_output, re.MULTILINE
    )
    if not allowed or all(name.strip() in allowed for name in actual):
        return None
    allowed_text = "、".join(allowed)
    return f"""审校下面已经合并的小学 DSKP 知识目录，只修正 LEVEL 2 层级归属。
本文件由领域分隔页明确声明的 LEVEL 2 完整集合是：{allowed_text}。
最终输出中每一个 LEVEL 2 必须严格等于上述名称之一。
任何其他 LEVEL 2 都是误提升的课题名：删除该 LEVEL 2 包装，但完整保留其下所有
LEVEL 3、LEVEL 4 和 SCOPE，并按原顺序移动到它前面最近的合法 LEVEL 2 下。
不得新增、删除或改写任何 LEVEL 3、LEVEL 4、SCOPE，不得改变原顺序。
只输出完整的 BEGIN_KNOWLEDGE_TREE 到 END_KNOWLEDGE_TREE 协议。"""
